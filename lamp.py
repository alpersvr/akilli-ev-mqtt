# lamp.py
# ------------------------------------------------------------
# VIRTUAL LAMP (Actuator)
#
# Waits for {"state": "on"} or {"state": "off"} on
# "home/living_room/lamp/command" and publishes its state to
# "home/living_room/lamp". The Actuator class in actuator.py does all the work.
# ------------------------------------------------------------

import config
from actuator import Actuator

if __name__ == "__main__":
    lamp = Actuator(
        device_id="living-room-lamp-01",
        label="LAMP",
        topic=config.LAMP_TOPIC,
        valid_states=["on", "off"],
        initial_state="off",
    )
    lamp.run()
