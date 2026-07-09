from fastapi import FastAPI
from pydantic import BaseModel
import json
import sqlite3




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

    c.execute("""
        SELECT id, name, battery, state
        FROM robots
        WHERE state = 'IDLE' AND battery >= 30
        LIMIT 1
    """)

    robot = c.fetchone()

    if robot is None:
        conn.close()
        return {"message": "No available AGV"}

    robot_id = robot[0]
    robot_name = robot[1]

    c.execute("""
        UPDATE robots
        SET state = 'ASSIGNED'
        WHERE id = ?
    """, (robot_id,))

    c.execute("""
        INSERT INTO tasks (id, pickup, dropoff, assigned_robot, status)
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
        SELECT assigned_robot
        FROM tasks
        WHERE id = ?
    """, (task_id,))

    task = c.fetchone()

    if task is None:
        conn.close()
        return {"message": "Task not found"}

    assigned_robot = task[0]

    c.execute("""
        UPDATE tasks
        SET status = 'DONE'
        WHERE id = ?
    """, (task_id,))

    c.execute("""
        UPDATE robots
        SET state = 'IDLE'
        WHERE name = ?
    """, (assigned_robot,))

    conn.commit()
    conn.close()

    return {
        "message": "Task completed",
        "task_id": task_id,
        "robot": assigned_robot
    }


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