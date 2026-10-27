# config.py
# ------------------------------------------------------------
# Shared project settings live in this file.
# If the broker address, topic names, automation thresholds etc.
# change, editing this file is enough; every other file reads
# its settings from here.
# ------------------------------------------------------------

# ============================================================
# BROKER CONNECTION
# ============================================================

# Address of the machine running the Mosquitto broker.
# The broker runs on our own computer, so we use "localhost".
BROKER_HOST = "localhost"

# 1883 is MQTT's default (unencrypted) port.
BROKER_PORT = 1883

# If the broker hears nothing from a client for this many seconds,
# it assumes the connection is lost. paho pings automatically within this time.
KEEPALIVE_SECONDS = 60

# Browsers cannot speak MQTT directly; they connect over WebSocket.
# Mosquitto listens on this port as well (see mosquitto.conf). Used by the stage 3 panel.
WEBSOCKET_PORT = 9001

# Port the panel web page is served on: http://localhost:8000
PANEL_PORT = 8000

# Message delivery guarantee level (0, 1 or 2).
# 1 = the message is delivered at least once. Stage 4 compares 0, 1 and 2.
QOS = 1

# ============================================================
# TOPICS
# Layout: home/<room>/<device>
#   - A device publishes its STATE to this topic.
#   - Actuators (lamp, AC, alarm) listen for COMMANDS on
#     "<topic>/command". E.g. home/living_room/lamp/command
# ============================================================

# Sensors (publish data only)
TEMPERATURE_TOPIC = "home/living_room/temperature"
OUTDOOR_TEMPERATURE_TOPIC = "home/outdoor/temperature"
MOTION_TOPIC = "home/living_room/motion"
DOOR_TOPIC = "home/entrance/door"

# Actuators (receive commands, publish their state)
LAMP_TOPIC = "home/living_room/lamp"
AC_TOPIC = "home/living_room/ac"
ALARM_TOPIC = "home/entrance/alarm"

# Command topic = device topic + this suffix
COMMAND_SUFFIX = "/command"

# Every device writes "online" here when it connects. If it drops
# unexpectedly, the broker writes "offline" automatically (Last Will).
# E.g. home/system/connection/living-room-lamp-01
CONNECTION_TOPIC_ROOT = "home/system/connection"

# Topic filter the subscriber listens to.
# The "#" wildcard covers ALL topics under "home/".
SUBSCRIBE_TOPIC = "home/#"

# ============================================================
# SIMULATION SETTINGS
# ============================================================

# How often (seconds) the temperature sensor publishes a reading.
PUBLISH_INTERVAL_SECONDS = 2

# Average outdoor temperature. The sensor slowly varies the outdoor
# temperature around this value; with the AC off the room drifts towards it.
# 30 = summer scenario (the AC cools). Set it to 12 for a winter
# scenario and you will see the AC switch to heating.
OUTDOOR_TEMPERATURE = 30.0

# The outdoor temperature can deviate from the average by at most this much (°C).
OUTDOOR_TEMPERATURE_RANGE = 3.0

# Probability per second that "someone entered the room" (0.05 = 5%).
MOTION_PROBABILITY = 0.05

# Probability per second, while the door is closed, that it opens (0.02 = 2%).
DOOR_OPEN_PROBABILITY = 0.02

# ============================================================
# AUTOMATION RULES
# ============================================================

# How many seconds after motion stops the lamp turns itself off.
LAMP_OFF_DELAY = 15

# AC thresholds (°C). Having different start and stop values
# (hysteresis) keeps the AC from constantly switching on and off.
AC_COOLING_START = 26.0   # start cooling when it rises to this
AC_COOLING_STOP = 23.0    # stop cooling when it drops to this
AC_HEATING_START = 19.0   # start heating when it drops to this
AC_HEATING_STOP = 22.0    # stop heating when it rises to this
