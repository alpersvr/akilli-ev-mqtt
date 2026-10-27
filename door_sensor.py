# door_sensor.py
# ------------------------------------------------------------
# VIRTUAL DOOR SENSOR (Publisher)
#
# In reality a magnetic sensor mounted on the door frame. Every now
# and then the door opens and closes again a few seconds later. It only
# sends a message when the state CHANGES: {"state": "open"} or {"state": "closed"}
# ------------------------------------------------------------

import random
import time

import common
import config

DEVICE_ID = "entrance-door-01"
LABEL = "DOOR"

door_open = False
close_time = 0.0


def publish_state(client):
    state = "open" if door_open else "closed"
    common.publish_json(client, config.DOOR_TOPIC,
                        {"device_id": DEVICE_ID, "state": state}, retain=True)
    print(f"[{LABEL}] Door {state.upper()}")


def step(client):
    """Called every second; decides whether the door opens or closes."""
    global door_open, close_time
    now = time.time()

    if not door_open and random.random() < config.DOOR_OPEN_PROBABILITY:
        # The door opened: it will stay open for 3-6 seconds.
        door_open = True
        close_time = now + random.uniform(3, 6)
        publish_state(client)

    elif door_open and now >= close_time:
        door_open = False
        publish_state(client)


if __name__ == "__main__":
    client = common.create_client(DEVICE_ID, LABEL, on_connected=publish_state)
    print(f"[{LABEL}] Door events will be reported to '{config.DOOR_TOPIC}'. (Quit: Ctrl+C)")
    common.run(client, DEVICE_ID, LABEL, step=step, interval=1)
