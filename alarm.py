# alarm.py
# ------------------------------------------------------------
# VIRTUAL ALARM (Actuator)
#
# It has three states:
#   disarmed  : The alarm is off and reacts to nothing
#   armed     : Nobody is home; if the door opens or motion is detected
#               the automation triggers the alarm
#   triggered : The siren is sounding; it won't stop until a
#               "disarmed" command arrives
#
# Command example (home/entrance/alarm/command): {"state": "armed"}
# ------------------------------------------------------------

import config
from actuator import Actuator


class Alarm(Actuator):
    """
    A special kind of Actuator. Unlike the base class, it prints
    a siren warning every few seconds while triggered.
    """

    def __init__(self):
        super().__init__(
            device_id="entrance-alarm-01",
            label="ALARM",
            topic=config.ALARM_TOPIC,
            valid_states=["disarmed", "armed", "triggered"],
            initial_state="disarmed",
        )
        self.counter = 0

    def step(self, client):
        # Called every second; while triggered, print a warning every 3 seconds.
        if self.state == "triggered":
            if self.counter % 3 == 0:
                print("[ALARM] *** SIREN SOUNDING! *** "
                      "(send a 'disarmed' command to silence it)")
            self.counter += 1
        else:
            self.counter = 0


if __name__ == "__main__":
    Alarm().run()
