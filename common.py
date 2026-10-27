# common.py
# ------------------------------------------------------------
# SHARED MQTT HELPERS USED BY EVERY DEVICE
#
# Every device program does the same things: connect to the broker,
# send JSON messages, shut down cleanly on Ctrl+C. Instead of writing
# that code in every file, we write it once here and use it everywhere.
# A bug only needs to be fixed in one place.
# ------------------------------------------------------------

import json
import time
from datetime import datetime

import paho.mqtt.client as mqtt

import config


def timestamp():
    """Returns the current time formatted as '2026-10-10T16:10:46'."""
    return datetime.now().isoformat(timespec="seconds")


def connection_topic(device_id):
    """Topic where the device's online/offline status is written."""
    return f"{config.CONNECTION_TOPIC_ROOT}/{device_id}"


def create_client(device_id, label, subscriptions=(), on_message=None, on_connected=None,
                  report_connection=True):
    """
    Creates and returns a configured MQTT client.

    device_id         : Unique name the broker knows this client by. CAREFUL: If a
                        second client connects with the same name, the broker drops the first!
    label             : Short name prefixed to printed lines, e.g. "LAMP"
    subscriptions     : List of topics to subscribe to after connecting
    on_message        : Function to call when a message arrives (optional)
    on_connected      : Extra function to call once connected (optional)
    report_connection : If True, online/offline status is published. We use True
                        for the home's devices and False for monitoring screens.
    """
    # userdata: a small note attached to the client that can be read later.
    # run() checks this on shutdown.
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=device_id,
                         userdata={"report_connection": report_connection})

    if report_connection:
        # LAST WILL: If the device drops unexpectedly (program crashes,
        # network goes away...) the broker publishes this message on our behalf.
        # retain=True: the broker keeps this message, so later subscribers see it too.
        client.will_set(connection_topic(device_id), "offline", qos=config.QOS, retain=True)

    def _on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[{label}] Connection refused, reason: {reason_code}")
            return
        print(f"[{label}] Connected to broker: {config.BROKER_HOST}:{config.BROKER_PORT}")
        if report_connection:
            client.publish(connection_topic(device_id), "online", qos=config.QOS, retain=True)

        # Subscriptions are made here: if the connection drops and is
        # re-established, the subscriptions are renewed automatically too.
        for topic in subscriptions:
            client.subscribe(topic, qos=config.QOS)
            print(f"[{label}] Listening on '{topic}'.")

        if on_connected:
            on_connected(client)

    def _on_disconnect(client, userdata, flags, reason_code, properties):
        # On a normal shutdown (our own disconnect() call) we print nothing.
        if reason_code.is_failure:
            print(f"[{label}] Connection lost ({reason_code}). Reconnecting...")

    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    if on_message:
        client.on_message = on_message
    return client


def publish_json(client, topic, data, retain=False):
    """
    Converts a dict to JSON text with a timestamp added, and publishes it.

    With retain=True the broker keeps the LAST message on this topic, so a
    program that connects later (e.g. the stage 3 panel) learns the device's
    current state right away. We use True for state messages, False for commands.
    """
    data = {**data, "timestamp": timestamp()}
    text = json.dumps(data, ensure_ascii=False)
    client.publish(topic, text, qos=config.QOS, retain=retain)
    return text


def parse_json(msg):
    """
    Converts the payload of an incoming MQTT message to a dict.
    Returns None if the payload is not a valid JSON object.
    """
    try:
        data = json.loads(msg.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def run(client, device_id, label, step=None, interval=1.0):
    """
    The program's main loop. Connects to the broker, calls 'step(client)'
    every 'interval' seconds until Ctrl+C is pressed, then closes the
    connection cleanly.
    """
    try:
        client.connect(config.BROKER_HOST, config.BROKER_PORT, config.KEEPALIVE_SECONDS)
    except ConnectionRefusedError:
        print(f"[{label}] ERROR: Could not connect to the broker. Is Mosquitto running?")
        return

    # Start the loop that handles network traffic in the background.
    client.loop_start()

    # Wait at most 5 seconds for the connection to complete.
    for _ in range(50):
        if client.is_connected():
            break
        time.sleep(0.1)

    try:
        while True:
            if step:
                step(client)
            time.sleep(interval)
    except KeyboardInterrupt:
        # We end up here when the user presses Ctrl+C.
        print(f"\n[{label}] Stopping...")
    finally:
        # The Last Will is not sent on a normal shutdown, so we publish
        # "offline" ourselves and wait for it to be delivered.
        if client.user_data_get()["report_connection"]:
            info = client.publish(connection_topic(device_id), "offline", qos=config.QOS, retain=True)
            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                info.wait_for_publish(timeout=2)
        # Close the connection first, then stop the background loop.
        client.disconnect()
        client.loop_stop()
        print(f"[{label}] Connection closed.")
