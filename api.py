from fastapi import FastAPI
from pydantic import BaseModel

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
    


fleet = [
    AGV("AGV-01", 80, "IDLE"),
    AGV("AGV-02", 25, "CHARGING"),
    AGV("AGV-03", 60, "IDLE")
]


@app.get("/")
def home():
    return {"message": "AGV Fleet API is running"}


@app.get("/robots")
def get_robots():
    return [agv.to_dict() for agv in fleet]

@app.post("/tasks")
def create_task(task:Task):
    for agv in fleet:
        if agv.assign_task(task.dict()):
            return {
                "message": "Task assigbed",
                "robot": agv.name,
                "task": task
            }

    return{
        "message": "No avaiable AGV"
    }