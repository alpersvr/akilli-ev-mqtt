# motion_sensor.py
# ------------------------------------------------------------
# VIRTUAL MOTION SENSOR (Publisher)
#
# Like a real PIR sensor, it reports whether there is motion in the room.
# At random intervals "someone enters the room", moves around for a few
# seconds, and then the motion ends. It only sends a message when the
# state CHANGES: {"state": "detected"} or {"state": "clear"}
# ------------------------------------------------------------

import random
import time

import common
import config

DEVICE_ID = "living-room-motion-01"
LABEL = "MOTION"

# The sensor's current state. These variables are shared between
# functions, so they are defined at the top of the file (globally).
motion_detected = False
motion_end_time = 0.0


def publish_state(client):
    state = "detected" if motion_detected else "clear"
    common.publish_json(client, config.MOTION_TOPIC,
                        {"device_id": DEVICE_ID, "state": state}, retain=True)
    print(f"[{LABEL}] Motion {state.upper()}")


def step(client):
    """Called every second; decides whether there is motion."""
    global motion_detected, motion_end_time
    now = time.time()

    if not motion_detected and random.random() < config.MOTION_PROBABILITY:
        # Someone entered the room: there will be motion for 3-8 seconds.
        motion_detected = True
        motion_end_time = now + random.uniform(3, 8)
        publish_state(client)

    elif motion_detected and now >= motion_end_time:
        # The motion period is over.
        motion_detected = False
        publish_state(client)


if __name__ == "__main__":
    client = common.create_client(DEVICE_ID, LABEL, on_connected=publish_state)
    print(f"[{LABEL}] Motion will be reported to '{config.MOTION_TOPIC}'. (Quit: Ctrl+C)")
    common.run(client, DEVICE_ID, LABEL, step=step, interval=1)
