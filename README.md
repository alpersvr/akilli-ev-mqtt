# MQTT-Based Smart Home Simulation

An MQTT-based smart home project that simulates every device in Python, with no hardware.
It uses a local **Mosquitto** broker and the **paho-mqtt** (2.x) client library.

| Stage | Content | Status |
|---|---|---|
| 1 | Virtual temperature sensor + subscriber that prints to the screen | ✅ |
| 2 | Door, motion, lamp, AC, alarm + automation rules | ✅ |
| 3 | Monitoring and control panel in the browser | ✅ |
| 4 | QoS 0/1/2 latency and loss experiment + plots | ✅ |

## Architecture

```
  SENSORS (measure)                                    ACTUATORS (change)
  temperature_sensor.py ─┐                          ┌──> lamp.py
  motion_sensor.py      ─┼──>  MOSQUITTO BROKER  <──┼──> air_conditioner.py
  door_sensor.py        ─┘          ▲     │         └──> alarm.py
                                    │     ▼
                      automation.py (rules)    subscriber.py (monitor)
                                    ▲
                                    │ WebSocket (port 9001)
                          Panel in the browser (panel/)
```

The panel in the browser is a separate MQTT client too. It connects to the broker over WebSocket and uses the same topics as the other programs.

No program knows any other directly. Everyone talks only to the broker.
Sensors publish data. The automation listens to that data and sends commands to the actuators according to its rules.
Actuators apply the command and publish their new state.

## Topic layout

| Topic | Published by | Example payload |
|---|---|---|
| `home/living_room/temperature` | Temperature sensor | `{"temperature": 24.5, "unit": "C", ...}` |
| `home/outdoor/temperature` | Temperature sensor (outdoor) | `{"temperature": 30.2, "unit": "C", ...}` |
| `home/living_room/motion` | Motion sensor | `{"state": "detected"}` / `"clear"` |
| `home/entrance/door` | Door sensor | `{"state": "open"}` / `"closed"` |
| `home/living_room/lamp` | Lamp | `{"state": "on"}` / `"off"` |
| `home/living_room/ac` | AC | `{"state": "off"}` / `"cooling"` / `"heating"` |
| `home/entrance/alarm` | Alarm | `{"state": "disarmed"}` / `"armed"` / `"triggered"` |
| `home/living_room/lamp/command` | Automation / user | `{"state": "on"}` |
| `home/living_room/ac/command` | Automation / user | `{"state": "cooling"}` |
| `home/entrance/alarm/command` | Automation / user | `{"state": "armed"}` |
| `home/system/connection/<device_id>` | Each device / broker | `online` / `offline` |

Every JSON message also carries `device_id` (for state messages) and a `timestamp` (e.g. `2026-10-10T16:10:46`, local time) added when it is published.

MQTT features used:

- **Retain:** State messages are kept on the broker. A program that connects later (e.g. the stage 3 panel) learns the latest state right away.
- **Last Will (LWT):** If a device drops unexpectedly, the broker publishes `offline` on its behalf.
- **Wildcard `#`:** `subscriber.py` receives every message in the home with a single subscription to `home/#`.

## Automation rules (`automation.py`)

| Rule | Condition | Action |
|---|---|---|
| 1. Smart lighting | Motion detected | Turn the lamp on |
| | No motion for 15 s | Turn the lamp off |
| 2. Climate control | Temperature ≥ 26 °C | AC cooling (turns off at 23 °C) |
| | Temperature ≤ 19 °C | AC heating (turns off at 22 °C) |
| 3. Security | Door opened or motion while the alarm is armed | Trigger the alarm |

The temperature sensor also listens to the AC's state. When the AC cools, the room really cools down; when it turns off, the room warms back up towards the outdoor temperature.
The outdoor temperature itself slowly wanders around `OUTDOOR_TEMPERATURE` (±`OUTDOOR_TEMPERATURE_RANGE`).
This shows a closed-loop thermostat on screen. All thresholds can be changed in `config.py`.

## Files

| File | What it does |
|---|---|
| `config.py` | Broker address, topic names, probabilities, rule thresholds. **All settings live here.** |
| `common.py` | Helpers everyone uses: creating a client, sending/parsing JSON, the main loop, clean shutdown. |
| `actuator.py` | Shared template (class) for the lamp/AC/alarm: listen for commands → change state → publish state. |
| `temperature_sensor.py` | Publishes the living room and outdoor temperature every 2 s. Simulates the AC's effect. |
| `motion_sensor.py` | Produces "someone entered the room" events at random times. |
| `door_sensor.py` | Opens and closes the door at random times. |
| `lamp.py` | Virtual lamp (on/off). |
| `air_conditioner.py` | Virtual AC (off/cooling/heating). |
| `alarm.py` | Virtual alarm (disarmed/armed/triggered). Prints a siren warning while triggered. |
| `automation.py` | The brain of the home: listens to every sensor and sends commands according to the rules. |
| `subscriber.py` | Monitor: prints every message under `home/#` in aligned columns. |
| `mosquitto.conf` | Project-specific broker settings: ports 1883 (Python) and 9001 (WebSocket, panel). |
| `panel.py` | Serves the panel at http://localhost:8000, opens the browser, and hands `config.py` to the page as `/config.json`. |
| `panel/index.html` | The panel's structure: cards, texts, buttons. |
| `panel/panel.css` | The panel's appearance (light/dark theme, phone layout). |
| `panel/panel.js` | The panel's behaviour: MQTT connection, updating the screen, chart, sending commands from buttons. |
| `panel/mqtt.min.js` | Ready-made MQTT library for the browser (mqtt.js 5.10.1). Bundled in the project, so no internet is needed. Not edited by hand. |
| `start_all.py` | Starts 7 programs (all except the subscriber and panel) with one command; Ctrl+C stops them all. |
| `network_simulator.py` | Network simulator for the experiment: sits between client and broker, adds delay and randomly drops the connection. |
| `qos_experiment.py` | Runs the QoS 0/1/2 experiment and writes the results as CSV to `results/<date-time>/`. |
| `qos_plots.py` | Produces the plots and the summary table from the experiment results. |
| `requirements.txt` | Required Python libraries (`paho-mqtt`, `matplotlib`). |

## Setup (once)

```bash
cd ~/akilli-ev-mqtt
python3 -m venv .venv                 # create a virtual environment
source .venv/bin/activate             # activate it
pip install -r requirements.txt       # install paho-mqtt and matplotlib
```

## Running

**Terminal 1: Broker (with the project settings)**

```bash
cd ~/akilli-ev-mqtt
mosquitto -c mosquitto.conf -v
```

The Python programs also work without `-c mosquitto.conf`, but then the WebSocket port (9001) used by the panel is not opened.

**Terminal 2: Monitor**

```bash
cd ~/akilli-ev-mqtt && source .venv/bin/activate
python subscriber.py
```

**Terminal 3: The whole home**

```bash
cd ~/akilli-ev-mqtt && source .venv/bin/activate
python start_all.py
```

**Terminal 4: Panel**

```bash
cd ~/akilli-ev-mqtt && source .venv/bin/activate
python panel.py
```

The browser opens by itself. If it doesn't, type http://localhost:8000 in the address bar.
The monitor in Terminal 2 is optional; the panel has an event log too.

You can also run the programs one by one if you like (`python lamp.py`, `python automation.py` ...). Each is independent.

To stop, press **Ctrl+C** in the relevant terminal.

## What's on the panel?

- **Living room climate:** Current indoor and outdoor temperature with the time of the last reading, and a chart of the last 3 minutes. The chart shows the outdoor temperature (dashed line), the automation thresholds, the moments the AC was running (blue/orange strip at the bottom) and time labels along the bottom. The AC mode can be changed here.
- **Lighting:** Turn the lamp on/off, motion state, how many seconds until the lamp turns off. The "Simulate motion" button publishes a 4 s motion event on behalf of the sensor.
- **Security:** Arm / disarm the alarm, door state, "Simulate door opening".
- **Devices:** Online/offline list built from Last Will messages. If you stop a device, a red "Offline" tag appears on its card.
- **Event log:** Every incoming MQTT message. Commands are highlighted with a blue row, and their source (panel, simulation) is shown in parentheses.

Every state on the panel shows when it last changed ("Last update 16:10:46 · 5 s ago"). This time comes from the message's `timestamp` field, so for retained messages it is the moment the state really changed, not the moment the page was opened. The event log's time column uses the same value; hover over it to see the full date.

**Demo suggestion:** Open the panel → arm the alarm with "Arm" → press "Simulate motion". The lamp turns on, the alarm goes off, and the event log shows the whole chain: sensor → automation command → actuator state.

**Note:** If a command from the panel contradicts the automation rules, the automation corrects it. For example, if you switch the AC to heating while the room is at 24 °C, the automation turns the AC off at the next reading (heating stops at 22 °C).

## Sending commands manually (from another terminal)

```bash
# Arm the alarm (you left home) -> it triggers when the door opens or there is motion
mosquitto_pub -t home/entrance/alarm/command -m '{"state":"armed"}'

# Silence / disarm the alarm
mosquitto_pub -t home/entrance/alarm/command -m '{"state":"disarmed"}'

# Turn the lamp on manually (the automation turns it off after 15 s without motion)
mosquitto_pub -t home/living_room/lamp/command -m '{"state":"on"}'

# Send a fake motion event (imitate the sensor)
mosquitto_pub -t home/living_room/motion -m '{"state":"detected"}'
```

**Winter scenario:** Set `OUTDOOR_TEMPERATURE = 12.0` in `config.py` and restart the programs. You'll see the AC switch to heating.

## Common errors

| Error | Fix |
|---|---|
| `ERROR: Could not connect to / reach the broker` | `mosquitto -c mosquitto.conf -v` must be running in Terminal 1. |
| The panel says "No broker connection" | Mosquitto was started without `-c mosquitto.conf`; the WebSocket port is closed. Stop it and restart it with the config file. |
| The panel opens but looks empty/old | Reload the page (Cmd+R). If you changed `config.py`, restart `panel.py`. |
| `Port 8000 is in use` | The panel is already open; no need to start it a second time. |
| `ModuleNotFoundError: No module named 'paho'` | The virtual environment isn't active. Run `source .venv/bin/activate`. |
| `Address already in use` (when starting mosquitto) | The broker is already running (probably via `brew services`). No need to start it again. |
| A program keeps printing "Connection lost" | You may have opened the same program twice. A second client connecting with the same `device_id` drops the first. |
| I changed the code but nothing changed | Running programs keep using the old code. Stop them with Ctrl+C and start them again. |

## Stage 4: QoS experiment

### What is measured?

A publisher sends 500 messages at a fixed rate (default 50 msg/s) and a subscriber receives them. Each message contains its sequence number and the moment it was sent.

| Metric | Definition |
|---|---|
| Latency | Time from when the message is sent until the subscriber receives it (end-to-end). |
| Loss | Share of messages that were sent but never arrived. |
| Duplicate | The same message arriving more than once. |

Publisher and subscriber run in the same program. Since both use the same clock, latency is measured with microsecond precision.

### Network scenarios

The network inside one computer (localhost) is perfect. In this environment there is no difference in loss between the three QoS levels. That's why `network_simulator.py` sits between the clients and the broker:

| Scenario | Condition |
|---|---|
| Ideal | Direct connection |
| Delayed | 40 ± 10 ms delay in each direction (like a slow mobile network) |
| Unstable | Delay + a sudden connection drop every 3 s on average (like Wi-Fi coming and going) |

MQTT runs over TCP, and TCP resends individually lost packets by itself. So in MQTT, real loss happens **when the connection drops**; the simulator creates loss the same way.
The QoS 0, 1 and 2 measurements of the same repetition use the same random seed, i.e. **connections that drop at the same moments**; the comparison is fair.

The experiment uses MQTT 5 and a persistent session. When the connection drops, the broker keeps the subscription and the undelivered QoS 1/2 messages. This is the only way the guarantee QoS promises actually works.

### Running

For a clean measurement, first stop the home's programs (`start_all.py`, panel). Start the broker **without** `-v`, because writing thousands of log lines slows the measurement down:

```bash
# Terminal 1
cd ~/akilli-ev-mqtt
mosquitto -c mosquitto.conf

# Terminal 2
cd ~/akilli-ev-mqtt && source .venv/bin/activate
pip install -r requirements.txt          # once, for matplotlib
python qos_experiment.py                 # ~7 minutes (3 scenarios × 3 QoS × 3 repetitions)
python qos_plots.py                      # produces the plots and the table
```

Options:
- `python qos_experiment.py --quick`: 100 messages, 1 repetition; finishes in about 1 minute, for trying it out.
- `--messages 1000 --rate 100 --repeat 5`: a longer and more reliable measurement.

### Outputs (`results/<date-time>/`)

| File | Content |
|---|---|
| `measurements.csv` | One row per message: scenario, QoS, repetition, sequence number, received or not, latency, duplicate count |
| `summary.csv` | One row per measurement: loss, duplicates, mean/median/p95/p99 latency, number of disconnects |
| `experiment_info.json` | Experiment parameters and software versions (for the "experimental setup" in a report) |
| `1_loss_rate.png` | Loss rate by scenario and QoS |
| `2_latency_distribution.png` | Latency distribution (box plot) |
| `3_latency_cdf.png` | What share of messages arrived within how long; the curve's ceiling also shows the loss |
| `summary.md` | Summary table that can be copied into a report |

### Expected results (and why)

| | QoS 0 | QoS 1 | QoS 2 |
|---|---|---|---|
| Guarantee | At most once | At least once | Exactly once |
| Handshake | None (PUBLISH) | 2 steps (PUBLISH → PUBACK) | 4 steps (PUBLISH → PUBREC → PUBREL → PUBCOMP) |
| Latency on a delayed network | ≈ 2 × one-way delay | Same as QoS 0 (the broker forwards without waiting for the PUBACK) | ≈ 3 times as long (the broker forwards the message when PUBREL arrives, and the same happens on the subscriber side) |
| Loss on disconnect | Yes | No | No |
| Duplicates on disconnect | No | **Possible** | No |
| Latency tail on disconnect | None (the message is simply lost) | Long (waits for the reconnect) | Long |

### A problem found during the experiment: silent loss with QoS 2

In the first trials, QoS 2 **lost** 14–26% of messages on the unstable network. According to QoS 2's guarantee this shouldn't happen. In the broker's verbose logs, this line appeared for every lost message:

```
Sending PUBREC to exp-pub-... (m68, rc151)     ← 151 = 0x97 "Quota exceeded"
```

**Why?** By default, Mosquitto lets a client have at most **20** QoS 1/2 messages awaiting acknowledgement at once (`max_inflight_messages 20`). paho-mqtt 2.1.0 sends all queued messages at once after a connection drops and is re-established: in the library's `_messages_reconnect_reset_out` function, the line that increments the counter is commented out. The broker rejects the messages beyond 20, and paho counts the message as "delivered" without checking this rejection code. With MQTT 3.1.1 the problem got even worse, because in that version the broker has no code to report the rejection.

**Fix:** `max_inflight_messages 0` (unlimited) in `mosquitto.conf`. With this setting QoS 2 worked **without loss and without duplicates** in every trial.

**Lesson:** The guarantee a protocol gives only holds when the broker and the client library work together correctly. Using QoS 2 does not by itself mean "messages are never lost"; the configuration and library behaviour must be tested too.
