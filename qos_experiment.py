# qos_experiment.py
# ------------------------------------------------------------
# QoS 0 / 1 / 2 LATENCY AND LOSS EXPERIMENT
#
# In each measurement:
#   1. A subscriber (receiver) and a publisher (sender) connect to the broker.
#   2. The publisher sends N messages at a fixed rate. Each message
#      contains its sequence number and the moment it was sent.
#   3. The subscriber records when each message arrives.
#        latency   = arrival time - send time
#        loss      = messages sent but never received
#        duplicate = messages received more than once with the same sequence number
#
# This is done for 3 network scenarios × 3 QoS levels × a few repetitions.
# Since publisher and subscriber run in the same program, both use the same
# clock, so latency can be measured with microsecond precision.
#
# Results are written as CSV to the "results/<date-time>/" folder.
# For plots, run afterwards: python qos_plots.py
# ------------------------------------------------------------

import argparse
import csv
import json
import os
import platform
import socket
import statistics
import threading
import time
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

import config
from network_simulator import NetworkSimulator

# ============================================================
# EXPERIMENT SETTINGS
# ============================================================

QOS_LEVELS = [0, 1, 2]

# Network scenarios. If "network" is None, clients connect to the broker directly.
SCENARIOS = [
    {"name": "ideal", "description": "Direct connection (localhost)", "network": None},
    {"name": "delayed", "description": "40 ± 10 ms delay in each direction",
     "network": {"delay_ms": 40, "jitter_ms": 10, "mean_disconnect_s": None}},
    {"name": "unstable", "description": "40 ± 10 ms delay + a connection drop every 3 s on average",
     "network": {"delay_ms": 40, "jitter_ms": 10, "mean_disconnect_s": 3}},
]

NETWORK_SIMULATOR_PORT = 1885  # Port the simulator listens on
PAYLOAD_SIZE = 64              # Size of each message in bytes (about the size of sensor data)
DRAIN_TIME_S = 20              # Max wait for late messages after sending finishes
SESSION_EXPIRY_S = 60          # How long the broker keeps the session (subscription + queue) after a drop


# ============================================================
# MQTT HELPERS
# ============================================================

def connect_client(client_id, host, port, on_message=None, on_connect=None):
    """
    Creates and connects an MQTT v5 client for the experiment.

    We use a persistent session: if the connection drops, the broker keeps
    this client's subscriptions and the QoS 1/2 messages it couldn't deliver
    for SESSION_EXPIRY_S. After reconnecting, it continues where it left off.
    This is the only way the guarantee QoS promises actually works.
    """
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, protocol=mqtt.MQTTv5)
    # If the connection drops, reconnect within 1-2 seconds
    client.reconnect_delay_set(min_delay=1, max_delay=2)
    if on_message:
        client.on_message = on_message
    if on_connect:
        client.on_connect = on_connect

    properties = Properties(PacketTypes.CONNECT)
    properties.SessionExpiryInterval = SESSION_EXPIRY_S
    # MQTT_CLEAN_START_FIRST_ONLY: start a clean session on the first connection,
    # resume the old session when reconnecting after a drop.
    client.connect(host, port, keepalive=10,
                   clean_start=mqtt.MQTT_CLEAN_START_FIRST_ONLY, properties=properties)
    client.loop_start()
    return client


def close_client(client):
    """Closes the connection and asks the broker to delete the session right away."""
    properties = Properties(PacketTypes.DISCONNECT)
    properties.SessionExpiryInterval = 0
    client.disconnect(properties=properties)
    client.loop_stop()


# ============================================================
# A SINGLE MEASUREMENT
# ============================================================

def run_measurement(scenario, qos, repetition, message_count, rate):
    """Runs one measurement for a scenario + QoS + repetition and returns the results."""
    id_suffix = f"{scenario['name']}-q{qos}-r{repetition}-{os.getpid()}"
    topic = f"experiment/{id_suffix}"  # Each measurement uses its own topic so they don't mix

    # 1) Start the network simulator if needed. Seed = repetition number: the
    #    QoS 0, 1, 2 measurements of the same repetition see the same disconnect times (fair comparison).
    network = None
    host, port = config.BROKER_HOST, config.BROKER_PORT
    if scenario["network"]:
        network = NetworkSimulator(NETWORK_SIMULATOR_PORT, config.BROKER_HOST, config.BROKER_PORT,
                                   seed=repetition, **scenario["network"])
        network.start()
        host, port = "127.0.0.1", NETWORK_SIMULATOR_PORT

    # 2) Subscriber: records the latency of every incoming message
    received = {}  # sequence number -> [latency_ms, latency_ms (duplicate), ...]
    lock = threading.Lock()
    subscriber_ready = threading.Event()

    def on_message(client, userdata, msg):
        arrival = time.perf_counter()
        data = json.loads(msg.payload)
        with lock:
            received.setdefault(data["seq"], []).append((arrival - data["t"]) * 1000)

    def on_subscriber_connect(client, userdata, flags, reason_code, properties):
        if not reason_code.is_failure:
            # If the session is resumed the subscription already exists; subscribing again is harmless.
            client.subscribe(topic, qos=qos)

    subscriber = connect_client(f"exp-sub-{id_suffix}", host, port,
                                on_message=on_message, on_connect=on_subscriber_connect)
    subscriber.on_subscribe = lambda *args: subscriber_ready.set()
    if not subscriber_ready.wait(timeout=10):
        raise RuntimeError("The subscriber could not complete its subscription.")

    publisher = connect_client(f"exp-pub-{id_suffix}", host, port)
    for _ in range(100):  # Wait at most 10 s for the connection
        if publisher.is_connected():
            break
        time.sleep(0.1)

    # 3) Send the messages at a fixed rate
    start = time.perf_counter()
    for seq in range(message_count):
        target_time = start + seq / rate
        wait = target_time - time.perf_counter()
        if wait > 0:
            time.sleep(wait)
        payload = json.dumps({"seq": seq, "t": time.perf_counter()})
        payload = payload.ljust(PAYLOAD_SIZE)  # Pad with spaces to a fixed size
        # While disconnected, a QoS 0 message is dropped immediately; QoS 1/2 are queued.
        publisher.publish(topic, payload, qos=qos)
    sending_done = time.perf_counter()

    # 4) Wait for late messages (QoS 1/2 are resent after a disconnect)
    while time.perf_counter() - sending_done < DRAIN_TIME_S:
        with lock:
            arrived = len(received)
        if arrived >= message_count:
            break
        # A lost QoS 0 message never arrives; wait briefly and give up.
        if qos == 0 and time.perf_counter() - sending_done > 2:
            break
        time.sleep(0.1)
    time.sleep(0.5)  # A short margin for duplicates arriving at the last moment

    # 5) Clean up
    close_client(publisher)
    close_client(subscriber)
    disconnects = 0
    if network:
        network.stop()
        disconnects = network.disconnect_count

    # 6) Compute the results
    with lock:
        duplicates = {s: len(l) - 1 for s, l in received.items()}
        first_latency = {s: l[0] for s, l in received.items()}
    latencies = sorted(first_latency.values())
    received_count = len(latencies)

    def percentile(p):
        if not latencies:
            return float("nan")
        return latencies[min(len(latencies) - 1, int(round(p / 100 * (len(latencies) - 1))))]

    summary = {
        "scenario": scenario["name"],
        "qos": qos,
        "repetition": repetition,
        "sent": message_count,
        "received": received_count,
        "lost": message_count - received_count,
        "loss_rate_percent": round(100 * (message_count - received_count) / message_count, 3),
        "duplicates": sum(duplicates.values()),
        "mean_ms": round(statistics.fmean(latencies), 3) if latencies else "",
        "median_ms": round(statistics.median(latencies), 3) if latencies else "",
        "p95_ms": round(percentile(95), 3) if latencies else "",
        "p99_ms": round(percentile(99), 3) if latencies else "",
        "max_ms": round(latencies[-1], 3) if latencies else "",
        "disconnects": disconnects,
        "send_duration_s": round(sending_done - start, 2),
    }
    rows = [
        {"scenario": scenario["name"], "qos": qos, "repetition": repetition, "seq": s,
         "received": int(s in first_latency),
         "latency_ms": round(first_latency[s], 4) if s in first_latency else "",
         "duplicates": duplicates.get(s, 0)}
        for s in range(message_count)
    ]
    return summary, rows


# ============================================================
# MAIN PROGRAM
# ============================================================

def port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="MQTT QoS 0/1/2 latency and loss experiment")
    parser.add_argument("--messages", type=int, default=500, help="Messages sent per measurement (default 500)")
    parser.add_argument("--rate", type=float, default=50, help="Messages sent per second (default 50)")
    parser.add_argument("--repeat", type=int, default=3, help="Repetitions of each measurement (default 3)")
    parser.add_argument("--quick", action="store_true", help="Quick trial: 100 messages, 1 repetition")
    args = parser.parse_args()
    if args.quick:
        args.messages, args.repeat = 100, 1

    if not port_open(config.BROKER_HOST, config.BROKER_PORT):
        print("ERROR: Could not reach the broker. First run 'mosquitto -c mosquitto.conf'.")
        return
    if port_open("127.0.0.1", NETWORK_SIMULATOR_PORT):
        print(f"ERROR: Port {NETWORK_SIMULATOR_PORT} is in use. Another experiment may be running.")
        return

    folder = Path(__file__).parent / "results" / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    folder.mkdir(parents=True)

    total = len(SCENARIOS) * len(QOS_LEVELS) * args.repeat
    estimated_min = total * (args.messages / args.rate + 4) / 60
    print(f"Starting experiment: {len(SCENARIOS)} scenarios × {len(QOS_LEVELS)} QoS × {args.repeat} repetitions = "
          f"{total} measurements, each {args.messages} messages @ {args.rate:g} msg/s.")
    print(f"Estimated time: ~{estimated_min:.0f} minutes. Results: {folder}\n")

    summaries, all_rows = [], []
    counter = 0
    for scenario in SCENARIOS:
        print(f"--- Scenario: {scenario['name']} ({scenario['description']}) ---")
        for repetition in range(1, args.repeat + 1):
            for qos in QOS_LEVELS:
                counter += 1
                summary, rows = run_measurement(scenario, qos, repetition, args.messages, args.rate)
                summaries.append(summary)
                all_rows.extend(rows)
                print(f"[{counter:>2}/{total}] QoS {qos} · rep {repetition}:  "
                      f"received {summary['received']}/{summary['sent']}  "
                      f"loss {summary['loss_rate_percent']:<6g}% dup {summary['duplicates']:<3} "
                      f"median {summary['median_ms'] or '-':>8} ms   p95 {summary['p95_ms'] or '-':>8} ms   "
                      f"drops {summary['disconnects']}")
                # Save intermediate results after every measurement so no data is lost if interrupted
                write_csv(folder / "summary.csv", summaries)
        print()

    write_csv(folder / "measurements.csv", all_rows)
    info = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "message_count": args.messages,
        "rate_msg_per_s": args.rate,
        "repetitions": args.repeat,
        "payload_size_bytes": PAYLOAD_SIZE,
        "scenarios": SCENARIOS,
        "mqtt_version": "5",
        "paho_mqtt": version("paho-mqtt"),
        "python": platform.python_version(),
        "operating_system": platform.platform(),
    }
    (folder / "experiment_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Done. Results are in '{folder}'.")
    print("To draw the plots:  python qos_plots.py")


if __name__ == "__main__":
    main()
