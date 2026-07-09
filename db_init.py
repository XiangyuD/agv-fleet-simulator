import sqlite3

conn = sqlite3.connect('fleet.db')

c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS robots(
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT NOT NULL,
battery INTEGER NOT NULL,
state TEXT NOT NULL
)
""")

c.execute("DELETE FROM robots")


c.execute("""
INSERT INTO robots(name, battery, state)
VALUES
    ('AGV-01', 80, 'IDLE'),
    ('AGV-02', 25, 'CHARGING'),
    ('AGV-03', 60, 'IDLE')
""")

c.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    pickup TEXT NOT NULL,
    dropoff TEXT NOT NULL,
    assigned_robot TEXT,
    status TEXT NOT NULL
)
""")

conn.commit()

c.execute("SELECT * FROM robots")

for robot in c.fetchall():
    print(robot)


conn.close()


print("open the databass")