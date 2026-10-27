# actuator.py
# ------------------------------------------------------------
# ACTUATOR TEMPLATE
#
# Sensors MEASURE the environment (temperature, motion...). Actuators
# CHANGE it (turn on a lamp, cool the room, sound an alarm).
#
# The lamp, AC and alarm all work the same way:
#   1. Wait for a command on "<topic>/command", e.g. {"state": "on"}
#   2. If the command is valid, change state
#   3. Publish the new state to "<topic>"
#
# We write this shared behaviour once here, as a class.
# lamp.py, air_conditioner.py and alarm.py use this class.
# ------------------------------------------------------------

import common
import config


class Actuator:
    def __init__(self, device_id, label, topic, valid_states, initial_state):
        """
        device_id     : Unique device name, e.g. "living-room-lamp-01"
        label         : Short name shown on screen, e.g. "LAMP"
        topic         : Topic the state is published to, e.g. "home/living_room/lamp"
        valid_states  : Accepted states, e.g. ["on", "off"]
        initial_state : State when the program starts
        """
        self.device_id = device_id
        self.label = label
        self.topic = topic
        self.command_topic = topic + config.COMMAND_SUFFIX
        self.valid_states = valid_states
        self.state = initial_state

        self.client = common.create_client(
            device_id,
            label,
            subscriptions=[self.command_topic],
            on_message=self._on_command,
            # Announce the current state as soon as we connect.
            on_connected=lambda client: self.publish_state(),
        )

    def publish_state(self):
        """Publishes the current state (retained)."""
        common.publish_json(self.client, self.topic,
                            {"device_id": self.device_id, "state": self.state},
                            retain=True)

    def _on_command(self, client, userdata, msg):
        """paho calls this when a message arrives on the command topic."""
        data = common.parse_json(msg)
        requested = data.get("state") if data else None

        if requested not in self.valid_states:
            print(f"[{self.label}] Ignored invalid command: {msg.payload.decode('utf-8', 'replace')}"
                  f"  (valid states: {', '.join(self.valid_states)})")
            return

        old = self.state
        self.state = requested
        if old != requested:
            self.state_changed(old, requested)
        # We publish even if the state stayed the same: this way the
        # sender knows its command was processed.
        self.publish_state()

    def state_changed(self, old, new):
        """Called when the state changes. Subclasses may print something different."""
        print(f"[{self.label}] {old} -> {new}")

    def step(self, client):
        """Called every second. Does nothing by default (the alarm uses it)."""
        pass

    def run(self):
        """Starts the device; runs until Ctrl+C."""
        print(f"[{self.label}] Initial state: {self.state}. "
              f"Waiting for commands on '{self.command_topic}'. (Quit: Ctrl+C)")
        common.run(self.client, self.device_id, self.label, step=self.step, interval=1)
