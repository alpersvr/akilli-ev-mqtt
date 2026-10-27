# automation.py
# ------------------------------------------------------------
# AUTOMATION HUB (both Subscriber and Publisher)
#
# The "brain" of the home. Listens to all sensors and device states
# and sends commands to the actuators according to these rules:
#
#   RULE 1 - Smart lighting:
#       If motion is detected, turn the lamp on. LAMP_OFF_DELAY
#       seconds after motion stops, turn the lamp off.
#
#   RULE 2 - Climate control (thermostat with hysteresis):
#       Temperature >= 26 °C  -> AC starts cooling, turns off at 23 °C
#       Temperature <= 19 °C  -> AC starts heating, turns off at 22 °C
#
#   RULE 3 - Security:
#       If the door opens or motion is detected while the alarm is
#       "armed", trigger the alarm.
#
# The devices don't know each other; they only talk to the broker.
# Since the rules are collected in one place, they are easy to change.
# ------------------------------------------------------------

import threading
import time

import common
import config

DEVICE_ID = "automation-hub"
LABEL = "AUTOMATION"

# Last known state of the home. None = no news from that device yet
# (e.g. its program isn't running). We don't send commands to unknown devices.
home = {
    "lamp": None,
    "ac": None,
    "alarm": None,
    "motion": "clear",
    # When the lamp's off-timer started (when motion stopped or the lamp turned on)
    "timer_start": 0.0,
}

# Messages run on paho's background thread, while the timer check runs
# in the main program. We use a lock so both don't modify the 'home'
# dict at the same time: whoever holds the lock finishes before the other proceeds.
lock = threading.Lock()


def send_command(client, device_topic, requested_state, reason):
    """Sends a command to an actuator and prints why."""
    print(f"[{LABEL}] {reason} -> {device_topic}: {requested_state}")
    common.publish_json(client, device_topic + config.COMMAND_SUFFIX, {"state": requested_state})


# ------------------------------------------------------------
# RULES
# ------------------------------------------------------------

def motion_changed(client, state, retained):
    home["motion"] = state
    if state == "clear":
        # Motion stopped: start the lamp's off-timer.
        home["timer_start"] = time.time()
        return

    # If this is an old message the broker kept (retain), it's not a new event.
    if retained:
        return

    # RULE 1: Motion and the lamp is off -> turn the lamp on
    if home["lamp"] == "off":
        send_command(client, config.LAMP_TOPIC, "on", "RULE 1: Motion detected")

    # RULE 3: Motion while the alarm is armed -> trigger the alarm
    if home["alarm"] == "armed":
        send_command(client, config.ALARM_TOPIC, "triggered", "RULE 3: Motion while the alarm is armed!")


def door_changed(client, state, retained):
    if state != "open" or retained:
        return
    # RULE 3: Door opened while the alarm is armed -> trigger the alarm
    if home["alarm"] == "armed":
        send_command(client, config.ALARM_TOPIC, "triggered", "RULE 3: Door opened while the alarm is armed!")


def temperature_changed(client, temperature):
    ac = home["ac"]
    if ac is None or temperature is None:
        return  # The AC program isn't running, or the data is broken

    # RULE 2: Thermostat with hysteresis
    if ac == "off":
        if temperature >= config.AC_COOLING_START:
            send_command(client, config.AC_TOPIC, "cooling", f"RULE 2: Room too hot ({temperature} °C)")
        elif temperature <= config.AC_HEATING_START:
            send_command(client, config.AC_TOPIC, "heating", f"RULE 2: Room too cold ({temperature} °C)")
    elif ac == "cooling" and temperature <= config.AC_COOLING_STOP:
        send_command(client, config.AC_TOPIC, "off", f"RULE 2: Room cool enough ({temperature} °C)")
    elif ac == "heating" and temperature >= config.AC_HEATING_STOP:
        send_command(client, config.AC_TOPIC, "off", f"RULE 2: Room warm enough ({temperature} °C)")


def lamp_changed(state):
    if state == "on" and home["lamp"] != "on":
        # The lamp was just turned on (manually or automatically): reset the
        # timer so it doesn't turn off immediately even without motion.
        home["timer_start"] = time.time()
    home["lamp"] = state


# ------------------------------------------------------------
# MQTT EVENTS
# ------------------------------------------------------------

def on_message(client, userdata, msg):
    """Called when a message arrives on any of the topics we listen to."""
    data = common.parse_json(msg)
    if data is None:
        return

    # msg.retain = True means this is an old state the broker kept
    # (published before we connected).
    with lock:
        if msg.topic == config.MOTION_TOPIC:
            motion_changed(client, data.get("state"), msg.retain)
        elif msg.topic == config.DOOR_TOPIC:
            door_changed(client, data.get("state"), msg.retain)
        elif msg.topic == config.TEMPERATURE_TOPIC:
            temperature_changed(client, data.get("temperature"))
        elif msg.topic == config.LAMP_TOPIC:
            lamp_changed(data.get("state"))
        elif msg.topic == config.AC_TOPIC:
            home["ac"] = data.get("state")
        elif msg.topic == config.ALARM_TOPIC:
            home["alarm"] = data.get("state")


def check_timer(client):
    """Called every second. The 'time's up, turn the lamp off' part of RULE 1."""
    with lock:
        elapsed = time.time() - home["timer_start"]
        if home["lamp"] == "on" and home["motion"] == "clear" and elapsed >= config.LAMP_OFF_DELAY:
            send_command(client, config.LAMP_TOPIC, "off",
                         f"RULE 1: No motion for {config.LAMP_OFF_DELAY} s")
            # Restart the timer so the command isn't sent over and over.
            home["timer_start"] = time.time()


if __name__ == "__main__":
    client = common.create_client(
        DEVICE_ID,
        LABEL,
        subscriptions=[
            config.TEMPERATURE_TOPIC,
            config.MOTION_TOPIC,
            config.DOOR_TOPIC,
            config.LAMP_TOPIC,
            config.AC_TOPIC,
            config.ALARM_TOPIC,
        ],
        on_message=on_message,
    )
    print(f"[{LABEL}] Rules active:\n"
          f"  RULE 1: Motion -> lamp on, {config.LAMP_OFF_DELAY} s without motion -> off\n"
          f"  RULE 2: >= {config.AC_COOLING_START} °C cool (stop at <= {config.AC_COOLING_STOP} °C), "
          f"<= {config.AC_HEATING_START} °C heat (stop at >= {config.AC_HEATING_STOP} °C)\n"
          f"  RULE 3: Door/motion while armed -> alarm triggered")
    common.run(client, DEVICE_ID, LABEL, step=check_timer, interval=1)
