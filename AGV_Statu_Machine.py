class AGV:
    def __init__(self, name):
        self.name = name
        self.state = "IDLE"
        self.battery = 100
        self.task = None
        self.location = "HOME"
        self.error_reason = None

    def show_status(self):
        print("--------------------")
        print(f"AGV Name: {self.name}")
        print(f"State: {self.state}")
        print(f"Battery: {self.battery}%")
        print(f"Task: {self.task}")
        print(f"Location: {self.location}")
        print("--------------------")

    def assign_task(self, task):
        if self.battery < 30:
            print("Battery too low, AGV needs charging")
            self.state = "CHARGING"
            return

        if self.state != "IDLE":
            print("AGV is busy, can't take new task")
            return

        self.task = task
        self.state = "ASSIGNED"

        print(f"Task assigned: {task['id']}")

    def trigger_error(self, reason):
        self.error_reason = reason
        self.state = "ERROR"
        print(f"ERROR: {reason}")

    def reset_error(self):
        if self.state == "ERROR":
            print("Error cleared")
            self.error_reason = None
            self.state = "IDLE"

    def step(self):
        print(f"\nCurrent State: {self.state}")

        if self.state == "IDLE":
            print("AGV is waiting for task")

        elif self.state == "ASSIGNED":
            print(f"AGV moving to {self.task['pickup']}")
            self.state = "MOVING_TO_PICKUP"

        elif self.state == "MOVING_TO_PICKUP":
            print("AGV arrived at pickup point")
            self.battery -= 10
            self.state = "PICKING"
            self.location = "pick up location"

        elif self.state == "PICKING":
            print("AGV picking load")
            self.state = "MOVING_TO_DROPOFF"

        elif self.state == "MOVING_TO_DROPOFF":
            print(f"AGV arrived at {self.task['dropoff']}")
            self.battery -= 10
            self.state = "DROPPING"

        elif self.state == "DROPPING":
            print(f"Task completed: {self.task['id']}")

            self.task = None
            self.state = "IDLE"
            self.location = "drop off locaiton"
        
        elif self.state == "CHARGING":
            print("AGV is charging...")
            self.battery += 20

            if self.battery >= 90:
                self.battery = 90
                self.state = "IDLE"
                print("AGV charged enough, back to IDEL")

        elif self.state == "ERROR":
            print(f"AGV stopped due to error: {self.error_reason}")

        print(f"Battery: {self.battery}%")


fleet = [
    AGV("AGV-01"),
    AGV("AGV-02"),
    AGV("AGV-03")
]

for agv in fleet:
    agv.show_status()

fleet[0].battery = 25
fleet[1].battery = 80
fleet[2].battery = 60

def find_available_agv(fleet):
    for agv in fleet:
        if agv.state == "IDLE" and agv.battery >= 30:
            print(f"{agv.name} is avaiable")
            return agv

    return None


task = {
    "id": "T004",
    "pickup": "Station A",
    "dropoff": "Station B"
}

available_agv = find_available_agv(fleet)

if available_agv is not None:
    available_agv.assign_task(task)
else:
    print("No available AGV")