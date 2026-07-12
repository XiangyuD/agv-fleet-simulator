from fastapi import FastAPI
from pydantic import BaseModel
import json
import sqlite3
from fastapi.responses import HTMLResponse




app = FastAPI()


class Task(BaseModel):
    id: str
    pickup: str
    dropoff: str




class AGV:
    def __init__(self, name, battery=100, state="IDLE"):
        self.name = name
        self.battery = battery
        self.state = state
        self.task = None

    def to_dict(self):
        return {
            "name": self.name,
            "battery": self.battery,
            "state": self.state,
            "task": self.task
        }

    def assign_task(self, task):
        if self.state != "IDLE":
            return False
        
        if self.battery < 30:
            self.state = "CHARGING"
            return False

        self.task = task
        self.state = "ASSIGNED"
        return True
    


def load_robots_from_db():
    conn = sqlite3.connect("fleet.db")
    c = conn.cursor()

    c.execute("SELECT id, name, battery, state FROM robots")
    rows = c.fetchall()

    conn.close()

    robots = []

    for row in rows:
        robot = {
            "id": row[0],
            "name": row[1],
            "battery": row[2],
            "state": row[3]
        }
        robots.append(robot)

    return robots

def load_fleet():
    with open("fleet.json", "r") as file:
        data = json.load(file)

    return [
        AGV(robot["name"], robot["battery"], robot["state"])
        for robot in data
    ]


def assign_task_to_db(task):
    conn = sqlite3.connect("fleet.db")
    c = conn.cursor()

    # 检查任务 ID 是否重复
    c.execute("""
        SELECT id
        FROM tasks
        WHERE id = ?
    """, (task.id,))

    existing_task = c.fetchone()

    if existing_task is not None:
        conn.close()
        return {
            "message": "Task ID already exists",
            "task_id": task.id
        }

    # 查找可用机器人
    c.execute("""
        SELECT id, name
        FROM robots
        WHERE state = 'IDLE' AND battery >= 30
        ORDER BY battery DESC
        LIMIT 1
    """)

    robot = c.fetchone()

    # 没有可用机器人：任务进入等待队列
    if robot is None:
        c.execute("""
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

    # 更新机器人状态
    c.execute("""
        UPDATE robots
        SET state = 'ASSIGNED'
        WHERE id = ?
    """, (robot_id,))

    # 保存任务
    c.execute("""
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


def complete_task_in_db(task_id):
    conn = sqlite3.connect("fleet.db")
    c = conn.cursor()

    c.execute("""
        SELECT assigned_robot, status
        FROM tasks
        WHERE id = ?
    """, (task_id,))

    task = c.fetchone()

    if task is None:
        conn.close()
        return {
            "message": "Task not found"
        }

    assigned_robot = task[0]
    task_status = task[1]

    if task_status == "DONE":
        conn.close()
        return {
            "message": "Task is already completed"
        }

    if task_status == "WAITING":
        conn.close()
        return {
            "message": "Waiting task cannot be completed"
        }

    # 将任务设置为完成
    c.execute("""
        UPDATE tasks
        SET status = 'DONE'
        WHERE id = ?
    """, (task_id,))

    # 每完成一个任务消耗 20% 电量
    c.execute("""
        UPDATE robots
        SET battery = MAX(battery - 20, 0)
        WHERE name = ?
    """, (assigned_robot,))

    # 获取扣电后的电量
    c.execute("""
        SELECT battery
        FROM robots
        WHERE name = ?
    """, (assigned_robot,))

    battery = c.fetchone()[0]

    # 低于 30% 自动充电，否则回到 IDLE
    if battery < 30:
        new_state = "CHARGING"
    else:
        new_state = "IDLE"

    c.execute("""
        UPDATE robots
        SET state = ?
        WHERE name = ?
    """, (new_state, assigned_robot))

    conn.commit()
    conn.close()

    next_task_id = None

    # 如果机器人仍然可用，自动接取等待任务
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

def dispatch_waiting_task(robot_name):
    conn = sqlite3.connect("fleet.db")
    c = conn.cursor()

    # 确认机器人当前可用
    c.execute("""
        SELECT id, battery, state
        FROM robots
        WHERE name = ?
    """, (robot_name,))

    robot = c.fetchone()

    if robot is None:
        conn.close()
        return None

    robot_id = robot[0]
    battery = robot[1]
    state = robot[2]

    if state != "IDLE" or battery < 30:
        conn.close()
        return None

    # 找最早进入队列的任务
    c.execute("""
        SELECT id
        FROM tasks
        WHERE status = 'WAITING'
        ORDER BY rowid ASC
        LIMIT 1
    """)

    waiting_task = c.fetchone()

    if waiting_task is None:
        conn.close()
        return None

    task_id = waiting_task[0]

    # 分配任务
    c.execute("""
        UPDATE tasks
        SET assigned_robot = ?, status = 'ASSIGNED'
        WHERE id = ?
    """, (robot_name, task_id))

    c.execute("""
        UPDATE robots
        SET state = 'ASSIGNED'
        WHERE id = ?
    """, (robot_id,))

    conn.commit()
    conn.close()

    return task_id

@app.get("/")
def home():
    return {"message": "AGV Fleet API is running"}


@app.get("/robots")
def get_robots():
    return load_robots_from_db()

    
# @app.post("/tasks")
# def create_task(task:Task):
#     for agv in fleet:
#         if agv.assign_task(task.dict()):
#             return {
#                 "message": "Task assigbed",
#                 "robot": agv.name,
#                 "task": task
#             }

#     return{
#         "message": "No avaiable AGV"
#     }

@app.post("/tasks")
def create_task(task: Task):
    return assign_task_to_db(task)


@app.get("/tasks")
def get_tasks():
    conn = sqlite3.connect("fleet.db")
    c = conn.cursor()

    c.execute("SELECT id, pickup, dropoff, assigned_robot, status FROM tasks")
    rows = c.fetchall()

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

@app.post("/tasks/{task_id}/complete")
def complete_task(task_id: str):
    return complete_task_in_db(task_id)

@app.post("/robots/{robot_name}/charge")
def charge_robot(robot_name: str):
    conn = sqlite3.connect("fleet.db")
    c = conn.cursor()

    c.execute("""
        SELECT battery, state
        FROM robots
        WHERE name = ?
    """, (robot_name,))

    robot = c.fetchone()

    if robot is None:
        conn.close()
        return {
            "message": "Robot not found"
        }

    battery = robot[0]

    new_battery = min(battery + 20, 100)

    if new_battery >= 80:
        new_state = "IDLE"
    else:
        new_state = "CHARGING"

    c.execute("""
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

    # 充到 80% 后自动尝试接等待任务
    if new_state == "IDLE":
        next_task_id = dispatch_waiting_task(robot_name)

    return {
        "message": "Robot charging updated",
        "robot": robot_name,
        "battery": new_battery,
        "state": new_state,
        "next_task": next_task_id
    }

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    robots = load_robots_from_db()

    conn = sqlite3.connect("fleet.db")
    c = conn.cursor()

    c.execute("""
        SELECT id, pickup, dropoff, assigned_robot, status
        FROM tasks
        ORDER BY rowid DESC
    """)

    task_rows = c.fetchall()
    conn.close()

    robot_table_rows = ""

    for robot in robots:
        robot_table_rows += f"""
        <tr>
            <td>{robot["id"]}</td>
            <td>{robot["name"]}</td>
            <td>{robot["battery"]}%</td>
            <td>{robot["state"]}</td>
        </tr>
        """

    task_table_rows = ""

    for task in task_rows:
        assigned_robot = task[3] if task[3] is not None else "-"

        task_table_rows += f"""
        <tr>
            <td>{task[0]}</td>
            <td>{task[1]}</td>
            <td>{task[2]}</td>
            <td>{assigned_robot}</td>
            <td>{task[4]}</td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>AGV Fleet Dashboard</title>

        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 40px;
                background: #f5f5f5;
            }}

            h1 {{
                margin-bottom: 30px;
            }}

            h2 {{
                margin-top: 30px;
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
                background: white;
            }}

            th, td {{
                border: 1px solid #dddddd;
                padding: 10px;
                text-align: left;
            }}

            th {{
                background: #eeeeee;
            }}
        </style>
    </head>

    <body>
        <h1>AGV Fleet Dashboard</h1>

        <h2>Robots</h2>

        <table>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Battery</th>
                <th>State</th>
            </tr>

            {robot_table_rows}
        </table>

        <h2>Tasks</h2>

        <table>
            <tr>
                <th>ID</th>
                <th>Pickup</th>
                <th>Dropoff</th>
                <th>Assigned Robot</th>
                <th>Status</th>
            </tr>

            {task_table_rows}
        </table>
    </body>
    </html>
    """