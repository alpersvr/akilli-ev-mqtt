# air_conditioner.py
# ------------------------------------------------------------
# VIRTUAL AIR CONDITIONER (Actuator)
#
# Waits for {"state": "cooling"}, {"state": "heating"} or
# {"state": "off"} on "home/living_room/ac/command".
# Publishes its state to "home/living_room/ac".
#
# The AC actually cooling/heating the room is simulated in
# temperature_sensor.py: the sensor listens to the AC's state and
# changes the temperature accordingly.
# ------------------------------------------------------------

import config
from actuator import Actuator

if __name__ == "__main__":
    ac = Actuator(
        device_id="living-room-ac-01",
        label="AC",
        topic=config.AC_TOPIC,
        valid_states=["off", "cooling", "heating"],
        initial_state="off",
    )
    ac.run()
