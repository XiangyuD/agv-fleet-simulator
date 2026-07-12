import sqlite3

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


app = FastAPI(
    title="AGV Fleet Management System",
    description="A lightweight AGV fleet simulator built with FastAPI and SQLite.",
    version="1.0.0"
)


# =========================================================
# Request Models
# =========================================================

class Task(BaseModel):
    id: str
    pickup: str
    dropoff: str


# =========================================================
# Database Helper Functions
# =========================================================

def load_robots_from_db():
    """
    Read all robots from the SQLite database.
    """

    conn = sqlite3.connect("fleet.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, battery, state
        FROM robots
        ORDER BY id
    """)

    rows = cursor.fetchall()
    conn.close()

    robots = []

    for row in rows:
        robots.append({
            "id": row[0],
            "name": row[1],
            "battery": row[2],
            "state": row[3]
        })

    return robots


def load_tasks_from_db():
    """
    Read all tasks from the SQLite database.
    """

    conn = sqlite3.connect("fleet.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, pickup, dropoff, assigned_robot, status
        FROM tasks
        ORDER BY rowid DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    tasks = []

    for row in rows:
        tasks.append({
            "id": row[0],
            "pickup": row[1],
            "dropoff": row[2],
            "assigned_robot": row[3],
            "status": row[4]
        })

    return tasks


# =========================================================
# Task Dispatch Logic
# =========================================================

def dispatch_waiting_task(robot_name: str):
    """
    Assign the oldest WAITING task to an available robot.
    """

    conn = sqlite3.connect("fleet.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, battery, state
        FROM robots
        WHERE name = ?
    """, (robot_name,))

    robot = cursor.fetchone()

    if robot is None:
        conn.close()
        return None

    robot_id = robot[0]
    battery = robot[1]
    state = robot[2]

    if state != "IDLE" or battery < 30:
        conn.close()
        return None

    cursor.execute("""
        SELECT id
        FROM tasks
        WHERE status = 'WAITING'
        ORDER BY rowid ASC
        LIMIT 1
    """)

    waiting_task = cursor.fetchone()

    if waiting_task is None:
        conn.close()
        return None

    task_id = waiting_task[0]

    cursor.execute("""
        UPDATE tasks
        SET assigned_robot = ?, status = 'ASSIGNED'
        WHERE id = ?
    """, (robot_name, task_id))

    cursor.execute("""
        UPDATE robots
        SET state = 'ASSIGNED'
        WHERE id = ?
    """, (robot_id,))

    conn.commit()
    conn.close()

    return task_id


def assign_task_to_db(task: Task):
    """
    Create a new task and assign it to an available robot.

    If no robot is available, save the task as WAITING.
    """

    conn = sqlite3.connect("fleet.db")
    cursor = conn.cursor()

    # Check whether the task ID already exists.
    cursor.execute("""
        SELECT id
        FROM tasks
        WHERE id = ?
    """, (task.id,))

    existing_task = cursor.fetchone()

    if existing_task is not None:
        conn.close()

        return {
            "message": "Task ID already exists",
            "task_id": task.id
        }

    # Find an available robot.
    cursor.execute("""
        SELECT id, name
        FROM robots
        WHERE state = 'IDLE'
          AND battery >= 30
        ORDER BY battery DESC
        LIMIT 1
    """)

    robot = cursor.fetchone()

    # No available robot: add task to queue.
    if robot is None:
        cursor.execute("""
            INSERT INTO tasks (
                id,
                pickup,
                dropoff,
                assigned_robot,
                status
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            task.id,
            task.pickup,
            task.dropoff,
            None,
            "WAITING"
        ))

        conn.commit()
        conn.close()

        return {
            "message": "No available AGV. Task added to queue.",
            "task": task.model_dump(),
            "status": "WAITING"
        }

    robot_id = robot[0]
    robot_name = robot[1]

    cursor.execute("""
        UPDATE robots
        SET state = 'ASSIGNED'
        WHERE id = ?
    """, (robot_id,))

    cursor.execute("""
        INSERT INTO tasks (
            id,
            pickup,
            dropoff,
            assigned_robot,
            status
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        task.id,
        task.pickup,
        task.dropoff,
        robot_name,
        "ASSIGNED"
    ))

    conn.commit()
    conn.close()

    return {
        "message": "Task assigned",
        "robot": robot_name,
        "task": task.model_dump()
    }


def complete_task_in_db(task_id: str):
    """
    Complete a task, reduce robot battery, and update robot state.

    If the robot remains available, automatically assign the next
    waiting task.
    """

    conn = sqlite3.connect("fleet.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT assigned_robot, status
        FROM tasks
        WHERE id = ?
    """, (task_id,))

    task = cursor.fetchone()

    if task is None:
        conn.close()

        return {
            "message": "Task not found",
            "task_id": task_id
        }

    assigned_robot = task[0]
    task_status = task[1]

    if task_status == "DONE":
        conn.close()

        return {
            "message": "Task is already completed",
            "task_id": task_id
        }

    if task_status == "WAITING":
        conn.close()

        return {
            "message": "A waiting task cannot be completed",
            "task_id": task_id
        }

    cursor.execute("""
        UPDATE tasks
        SET status = 'DONE'
        WHERE id = ?
    """, (task_id,))

    # Each completed task consumes 20% battery.
    cursor.execute("""
        UPDATE robots
        SET battery = MAX(battery - 20, 0)
        WHERE name = ?
    """, (assigned_robot,))

    cursor.execute("""
        SELECT battery
        FROM robots
        WHERE name = ?
    """, (assigned_robot,))

    battery_result = cursor.fetchone()

    if battery_result is None:
        conn.close()

        return {
            "message": "Assigned robot not found",
            "task_id": task_id
        }

    battery = battery_result[0]

    if battery < 30:
        new_state = "CHARGING"
    else:
        new_state = "IDLE"

    cursor.execute("""
        UPDATE robots
        SET state = ?
        WHERE name = ?
    """, (new_state, assigned_robot))

    conn.commit()
    conn.close()

    next_task_id = None

    if new_state == "IDLE":
        next_task_id = dispatch_waiting_task(assigned_robot)

    return {
        "message": "Task completed",
        "task_id": task_id,
        "robot": assigned_robot,
        "battery": battery,
        "robot_state": new_state,
        "next_task": next_task_id
    }


def charge_robot_in_db(robot_name: str):
    """
    Increase robot battery by 20%.

    Once the battery reaches 80%, the robot becomes IDLE and may
    automatically receive a waiting task.
    """

    conn = sqlite3.connect("fleet.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT battery, state
        FROM robots
        WHERE name = ?
    """, (robot_name,))

    robot = cursor.fetchone()

    if robot is None:
        conn.close()

        return {
            "message": "Robot not found",
            "robot": robot_name
        }

    current_battery = robot[0]
    new_battery = min(current_battery + 20, 100)

    if new_battery >= 80:
        new_state = "IDLE"
    else:
        new_state = "CHARGING"

    cursor.execute("""
        UPDATE robots
        SET battery = ?, state = ?
        WHERE name = ?
    """, (
        new_battery,
        new_state,
        robot_name
    ))

    conn.commit()
    conn.close()

    next_task_id = None

    if new_state == "IDLE":
        next_task_id = dispatch_waiting_task(robot_name)

    return {
        "message": "Robot charging updated",
        "robot": robot_name,
        "battery": new_battery,
        "state": new_state,
        "next_task": next_task_id
    }


# =========================================================
# API Endpoints
# =========================================================

@app.get("/")
def home():
    return {
        "message": "AGV Fleet API is running",
        "docs": "/docs",
        "dashboard": "/dashboard"
    }


@app.get("/robots")
def get_robots():
    return load_robots_from_db()


@app.get("/tasks")
def get_tasks():
    return load_tasks_from_db()


@app.post("/tasks")
def create_task(task: Task):
    return assign_task_to_db(task)


@app.post("/tasks/{task_id}/complete")
def complete_task(task_id: str):
    return complete_task_in_db(task_id)


@app.post("/robots/{robot_name}/charge")
def charge_robot(robot_name: str):
    return charge_robot_in_db(robot_name)


# =========================================================
# Dashboard
# =========================================================

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    robots = load_robots_from_db()
    tasks = load_tasks_from_db()

    total_robots = len(robots)
    idle_robots = sum(
        1 for robot in robots
        if robot["state"] == "IDLE"
    )
    assigned_robots = sum(
        1 for robot in robots
        if robot["state"] == "ASSIGNED"
    )
    charging_robots = sum(
        1 for robot in robots
        if robot["state"] == "CHARGING"
    )

    robot_table_rows = ""

    for robot in robots:
        battery = robot["battery"]

        if battery >= 70:
            battery_class = "battery-high"
        elif battery >= 30:
            battery_class = "battery-medium"
        else:
            battery_class = "battery-low"

        state = robot["state"]

        if state == "IDLE":
            state_class = "status-idle"
        elif state == "ASSIGNED":
            state_class = "status-assigned"
        elif state == "CHARGING":
            state_class = "status-charging"
        else:
            state_class = "status-default"

        robot_table_rows += f"""
        <tr>
            <td>{robot["id"]}</td>
            <td><strong>{robot["name"]}</strong></td>

            <td>
                <span class="battery {battery_class}">
                    {battery}%
                </span>
            </td>

            <td>
                <span class="status {state_class}">
                    {state}
                </span>
            </td>
        </tr>
        """

    task_table_rows = ""

    for task in tasks:
        assigned_robot = (
            task["assigned_robot"]
            if task["assigned_robot"] is not None
            else "—"
        )

        status = task["status"]

        if status == "ASSIGNED":
            task_status_class = "task-assigned"
        elif status == "WAITING":
            task_status_class = "task-waiting"
        elif status == "DONE":
            task_status_class = "task-done"
        else:
            task_status_class = "status-default"

        task_table_rows += f"""
        <tr>
            <td><strong>{task["id"]}</strong></td>
            <td>{task["pickup"]}</td>
            <td>{task["dropoff"]}</td>
            <td>{assigned_robot}</td>

            <td>
                <span class="status {task_status_class}">
                    {status}
                </span>
            </td>
        </tr>
        """

    if not robot_table_rows:
        robot_table_rows = """
        <tr>
            <td colspan="4" class="empty-message">
                No robots found.
            </td>
        </tr>
        """

    if not task_table_rows:
        task_table_rows = """
        <tr>
            <td colspan="5" class="empty-message">
                No tasks found.
            </td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>

    <html lang="en">

    <head>
        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0"
        >

        <meta http-equiv="refresh" content="5">

        <title>AGV Fleet Dashboard</title>

        <style>
            * {{
                box-sizing: border-box;
            }}

            body {{
                margin: 0;
                padding: 0;
                font-family:
                    Arial,
                    Helvetica,
                    sans-serif;
                background: #f3f5f8;
                color: #1f2937;
            }}

            .container {{
                width: min(1200px, 92%);
                margin: 40px auto;
            }}

            .header {{
                margin-bottom: 30px;
            }}

            .header h1 {{
                margin: 0;
                font-size: 32px;
                color: #172033;
            }}

            .header p {{
                margin-top: 8px;
                color: #667085;
            }}

            .stats-grid {{
                display: grid;
                grid-template-columns:
                    repeat(4, minmax(0, 1fr));
                gap: 18px;
                margin-bottom: 30px;
            }}

            .stat-card {{
                background: white;
                padding: 22px;
                border-radius: 12px;
                box-shadow:
                    0 5px 18px rgba(16, 24, 40, 0.07);
                border: 1px solid #eaecf0;
            }}

            .stat-label {{
                color: #667085;
                font-size: 14px;
                margin-bottom: 8px;
            }}

            .stat-value {{
                font-size: 30px;
                font-weight: bold;
                color: #172033;
            }}

            .panel {{
                background: white;
                border-radius: 12px;
                box-shadow:
                    0 5px 18px rgba(16, 24, 40, 0.07);
                border: 1px solid #eaecf0;
                overflow: hidden;
                margin-bottom: 28px;
            }}

            .panel-header {{
                padding: 20px 24px;
                border-bottom: 1px solid #eaecf0;
            }}

            .panel-header h2 {{
                margin: 0;
                font-size: 20px;
            }}

            .table-wrapper {{
                overflow-x: auto;
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
            }}

            th {{
                background: #f9fafb;
                color: #475467;
                font-size: 13px;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                text-align: left;
                padding: 14px 20px;
                border-bottom: 1px solid #eaecf0;
            }}

            td {{
                padding: 16px 20px;
                border-bottom: 1px solid #f0f1f3;
                color: #344054;
            }}

            tr:last-child td {{
                border-bottom: none;
            }}

            tr:hover td {{
                background: #fafbfc;
            }}

            .status,
            .battery {{
                display: inline-block;
                padding: 6px 10px;
                border-radius: 999px;
                font-size: 13px;
                font-weight: bold;
            }}

            .battery-high {{
                background: #ecfdf3;
                color: #027a48;
            }}

            .battery-medium {{
                background: #fffaeb;
                color: #b54708;
            }}

            .battery-low {{
                background: #fef3f2;
                color: #b42318;
            }}

            .status-idle {{
                background: #ecfdf3;
                color: #027a48;
            }}

            .status-assigned {{
                background: #eff8ff;
                color: #175cd3;
            }}

            .status-charging {{
                background: #fff6ed;
                color: #c4320a;
            }}

            .task-assigned {{
                background: #eff8ff;
                color: #175cd3;
            }}

            .task-waiting {{
                background: #fffaeb;
                color: #b54708;
            }}

            .task-done {{
                background: #f2f4f7;
                color: #475467;
            }}

            .status-default {{
                background: #f2f4f7;
                color: #475467;
            }}

            .empty-message {{
                text-align: center;
                color: #98a2b3;
                padding: 32px;
            }}

            .footer {{
                text-align: center;
                color: #98a2b3;
                font-size: 13px;
                padding: 10px 0 30px;
            }}

            @media (max-width: 800px) {{
                .stats-grid {{
                    grid-template-columns:
                        repeat(2, minmax(0, 1fr));
                }}

                .header h1 {{
                    font-size: 26px;
                }}
            }}

            @media (max-width: 500px) {{
                .stats-grid {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
    </head>

    <body>
        <div class="container">

            <div class="header">
                <h1>AGV Fleet Management System</h1>

                <p>
                    Built with Python, FastAPI and SQLite.
                    This page refreshes automatically every 5 seconds.
                </p>
            </div>

            <div class="stats-grid">

                <div class="stat-card">
                    <div class="stat-label">
                        Total Robots
                    </div>

                    <div class="stat-value">
                        {total_robots}
                    </div>
                </div>

                <div class="stat-card">
                    <div class="stat-label">
                        Idle
                    </div>

                    <div class="stat-value">
                        {idle_robots}
                    </div>
                </div>

                <div class="stat-card">
                    <div class="stat-label">
                        Assigned
                    </div>

                    <div class="stat-value">
                        {assigned_robots}
                    </div>
                </div>

                <div class="stat-card">
                    <div class="stat-label">
                        Charging
                    </div>

                    <div class="stat-value">
                        {charging_robots}
                    </div>
                </div>

            </div>

            <div class="panel">

                <div class="panel-header">
                    <h2>Robots</h2>
                </div>

                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Name</th>
                                <th>Battery</th>
                                <th>State</th>
                            </tr>
                        </thead>

                        <tbody>
                            {robot_table_rows}
                        </tbody>
                    </table>
                </div>

            </div>

            <div class="panel">

                <div class="panel-header">
                    <h2>Tasks</h2>
                </div>

                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Pickup</th>
                                <th>Dropoff</th>
                                <th>Assigned Robot</th>
                                <th>Status</th>
                            </tr>
                        </thead>

                        <tbody>
                            {task_table_rows}
                        </tbody>
                    </table>
                </div>

            </div>

            <div class="footer">
                AGV Fleet Simulator · FastAPI · SQLite
            </div>

        </div>
    </body>

    </html>
    """