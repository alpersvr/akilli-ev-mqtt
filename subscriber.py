# subscriber.py
# ------------------------------------------------------------
# SUBSCRIBER / MONITOR
#
# Connects to the broker, subscribes to "home/#" and prints ALL
# messages in the home (sensor data, device states, commands,
# connection info) in a readable form. Used to watch what's going
# on in the system; it doesn't control anything.
# ------------------------------------------------------------

import os
from datetime import datetime

import common
import config

# Add the process ID (PID) to the client ID so several monitors can be
# open at once. With identical IDs the broker would drop the old one
# every time a new one connects.
DEVICE_ID = f"monitor-subscriber-{os.getpid()}"
LABEL = "SUBSCRIBER"


def on_message(client, userdata, msg):
    """
    paho calls this function for every message on a subscribed topic.
    msg.topic   -> the topic the message came on (e.g. home/living_room/temperature)
    msg.payload -> the message content (arrives as bytes)
    msg.retain  -> True if this is an old (last known) message kept by the broker
    """
    now = datetime.now().strftime("%H:%M:%S")
    data = common.parse_json(msg)

    # Make the message content short and readable depending on its type.
    if data is None:
        # Not JSON (e.g. plain text like "online")
        content = msg.payload.decode("utf-8", "replace")
    elif "temperature" in data:
        content = f"{data['temperature']} °{data.get('unit', 'C')}"
    elif "state" in data:
        content = data["state"]
    else:
        content = str(data)

    if msg.topic.endswith(config.COMMAND_SUFFIX):
        content = f"COMMAND: {content}"
    if msg.retain:
        content += "  (retained last state)"

    # :<49 -> left-align the topic in a 49-character field (so columns line up;
    # the longest topic is home/system/connection/living-room-temperature-01)
    print(f"[{now}] {msg.topic:<49} {content}")


if __name__ == "__main__":
    client = common.create_client(
        DEVICE_ID,
        LABEL,
        subscriptions=[config.SUBSCRIBE_TOPIC],
        on_message=on_message,
        report_connection=False,  # The monitor is not one of the home's devices
    )
    print(f"[{LABEL}] Waiting for messages... (Quit: Ctrl+C)")
    common.run(client, DEVICE_ID, LABEL)
