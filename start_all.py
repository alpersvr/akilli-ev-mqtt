# start_all.py
# ------------------------------------------------------------
# START EVERY DEVICE WITH ONE COMMAND
#
# Instead of opening 7 programs in 7 separate terminals, this file
# starts them all at once as separate processes. Each device is still
# its own independent MQTT client, just like in a real home.
# Pressing Ctrl+C shuts them all down cleanly together.
#
# subscriber.py is NOT in this list: open it in a separate terminal to
# watch all the home's traffic on a clean screen.
# ------------------------------------------------------------

import socket
import subprocess
import sys
import time
from pathlib import Path

import config

# Actuators and automation start first so they don't miss the sensors' first messages.
PROGRAMS = [
    "lamp.py",
    "air_conditioner.py",
    "alarm.py",
    "automation.py",
    "temperature_sensor.py",
    "motion_sensor.py",
    "door_sensor.py",
]


def broker_running():
    """Checks whether the broker is running by briefly connecting to its port."""
    try:
        with socket.create_connection((config.BROKER_HOST, config.BROKER_PORT), timeout=2):
            return True
    except OSError:
        return False


def main():
    if not broker_running():
        print("ERROR: Could not reach the broker. First run 'mosquitto -c mosquitto.conf -v' in another terminal.")
        return

    folder = Path(__file__).parent
    processes = []
    for program in PROGRAMS:
        # sys.executable = the Python currently in use (the one in the virtual environment)
        # -u = write output to the screen immediately, without buffering
        processes.append(subprocess.Popen([sys.executable, "-u", str(folder / program)], cwd=folder))
        time.sleep(0.3)

    print(f"\n>>> {len(processes)} programs running. Press Ctrl+C to stop them all <<<\n")

    try:
        # Wait until one of the programs exits unexpectedly.
        while all(p.poll() is None for p in processes):
            time.sleep(0.5)
        print("\nA program exited unexpectedly; stopping the others too...")
        for p in processes:
            if p.poll() is None:
                p.terminate()
    except KeyboardInterrupt:
        # Ctrl+C in the terminal already sends the signal to every program;
        # we just wait for all of them to exit.
        print("\nStopping all programs...")

    for p in processes:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    print("All stopped.")


if __name__ == "__main__":
    main()
