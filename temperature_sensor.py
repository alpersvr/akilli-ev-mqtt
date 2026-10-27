# temperature_sensor.py
# ------------------------------------------------------------
# VIRTUAL TEMPERATURE SENSOR (Publisher)
#
# Instead of a real sensor, a program that produces realistic
# temperature values and sends a reading to the MQTT broker at
# regular intervals.
#
# Added in stage 2: the sensor also listens to the AC's state.
# That gives the simulation some "room physics":
#   - AC off     -> the room slowly approaches the outdoor temperature
#   - AC cooling -> the room cools down
#   - AC heating -> the room warms up
#
# It also simulates the outdoor temperature: it produces a value that
# slowly wanders around config.OUTDOOR_TEMPERATURE and publishes it
# to a separate topic.
# ------------------------------------------------------------

import random

import common
import config

# This device's unique name. The broker identifies each client by it.
DEVICE_ID = "living-room-temperature-01"
LABEL = "TEMPERATURE"

temperature = 24.0     # Initial temperature
outdoor_temperature = config.OUTDOOR_TEMPERATURE
ac_state = "off"       # Assume the AC is off until we hear from it


def on_ac_message(client, userdata, msg):
    """Called when the AC publishes its state; we note the latest state."""
    global ac_state
    data = common.parse_json(msg)
    if data and "state" in data:
        ac_state = data["state"]


def next_outdoor_temperature(current):
    """
    The outdoor temperature changes randomly a little each step, but is
    pulled gently towards the average, so it wanders realistically
    around OUTDOOR_TEMPERATURE.
    """
    change = random.uniform(-0.15, 0.15) + (config.OUTDOOR_TEMPERATURE - current) * 0.02
    low = config.OUTDOOR_TEMPERATURE - config.OUTDOOR_TEMPERATURE_RANGE
    high = config.OUTDOOR_TEMPERATURE + config.OUTDOOR_TEMPERATURE_RANGE
    return round(max(low, min(high, current + change)), 1)


def next_temperature(current, ac, outdoor):
    """
    Computes the next reading. Adds a little random 'noise' so the
    values jitter slightly like a real sensor.
    """
    noise = random.uniform(-0.1, 0.1)

    if ac == "cooling":
        change = -0.4
    elif ac == "heating":
        change = +0.4
    else:
        # With the AC off, the bigger the difference, the faster it warms/cools.
        change = (outdoor - current) * 0.05

    new = current + change + noise
    new = max(10.0, min(40.0, new))  # Keep the value in a sensible range
    return round(new, 1)             # 1 decimal place


def step(client):
    """Called every PUBLISH_INTERVAL_SECONDS seconds: measure and publish."""
    global temperature, outdoor_temperature
    outdoor_temperature = next_outdoor_temperature(outdoor_temperature)
    temperature = next_temperature(temperature, ac_state, outdoor_temperature)

    # Prepare the message as JSON and publish it. Thanks to retain=True,
    # programs that connect later receive the latest reading immediately.
    text = common.publish_json(client, config.TEMPERATURE_TOPIC,
                               {"device_id": DEVICE_ID, "temperature": temperature, "unit": "C"},
                               retain=True)
    print(f"[{LABEL}] Sent -> {config.TEMPERATURE_TOPIC}: {text}")

    text = common.publish_json(client, config.OUTDOOR_TEMPERATURE_TOPIC,
                               {"device_id": DEVICE_ID, "temperature": outdoor_temperature, "unit": "C"},
                               retain=True)
    print(f"[{LABEL}] Sent -> {config.OUTDOOR_TEMPERATURE_TOPIC}: {text}")


# This part runs when the file is executed directly (python temperature_sensor.py).
if __name__ == "__main__":
    client = common.create_client(
        DEVICE_ID,
        LABEL,
        subscriptions=[config.AC_TOPIC],
        on_message=on_ac_message,
    )
    print(f"[{LABEL}] Publishing to '{config.TEMPERATURE_TOPIC}' every "
          f"{config.PUBLISH_INTERVAL_SECONDS} seconds. (Quit: Ctrl+C)")
    common.run(client, DEVICE_ID, LABEL, step=step, interval=config.PUBLISH_INTERVAL_SECONDS)
