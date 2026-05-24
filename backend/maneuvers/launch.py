import krpc # type: ignore
import math
import time
from telemetry import TLM

########## Helpers

def safe_connect(name):
  try:
    conn = krpc.connect(name=name)
  except ConnectionRefusedError:
    print("!== Error making connection. Is there a reachable kRPC running in KSP? ==!")
    return False, False
  
  vessel = conn.space_center.active_vessel
  return conn, vessel

def wait_one_hour():
  conn, _vessel = safe_connect("Launch")
  if not conn: return

  ut = conn.add_stream(getattr, conn.space_center, 'ut') # Seems to be "Universal Time" see add_node in use

  conn.space_center.warp_to(ut() + 60*60)
  conn.close()

def vessel_is_down(vessel):
  return vessel.situation in (
      vessel.situation.landed,
      vessel.situation.splashed,
  )

def stage_has_engine(vessel, stage_number):
    return any(
        engine.part.stage == stage_number
        for engine in vessel.parts.engines
    )

def estimate_full_throttle_burn_time(vessel):
  propellant_requirements = {}

  active_engines = [
    engine
    for engine in vessel.parts.engines
    if engine.active and engine.available_thrust > 0
  ]

  for engine in active_engines:
    for propellant in engine.propellants:
      if propellant.current_requirement <= 0:
        continue

      if propellant.name not in propellant_requirements:
        propellant_requirements[propellant.name] = {
          "available": propellant.total_resource_available,
          "required": 0,
        }

      propellant_requirements[propellant.name]["required"] += propellant.current_requirement

  burn_times = [
    data["available"] / data["required"]
    for data in propellant_requirements.values()
    if data["required"] > 0
  ]

  if not burn_times:
    return 0

  return min(burn_times)

########## Mini-Maneuvers
def launch(conn, vessel):
  TLM.update("Pre-flight check")
  vessel.control.sas = False
  vessel.control.rcs = False
  vessel.control.throttle = 1.0
  time.sleep(3)

  TLM.update("Launching in 3..."); time.sleep(1)
  TLM.update("Launching in 2..."); time.sleep(1)
  TLM.update("Launching in 1..."); time.sleep(1)

  vessel.control.activate_next_stage()
  vessel.auto_pilot.engage()
  vessel.auto_pilot.target_pitch_and_heading(90, 90)
  vessel.auto_pilot.target_roll = 0

  while TLM.read("altitude") < 1000:
    TLM.update("Vertical Ascent")
    time.sleep(0.1)

def gravity_turn_to_orbit(conn, vessel):
  TLM.update("Pitch over")
  vessel.auto_pilot.target_pitch_and_heading(75, 90)
  time.sleep(7)

  vessel.auto_pilot.reference_frame = vessel.surface_velocity_reference_frame
  vessel.auto_pilot.target_direction = (0, 1, 0)
  vessel.auto_pilot.target_roll = 0

  while TLM.read("apoapsis") < 80000:
    TLM.update("Staging to space")

    current_stage = vessel.control.current_stage
    next_stage = current_stage - 1

    if vessel.available_thrust < 0.1 and stage_has_engine(vessel, next_stage):
      vessel.control.activate_next_stage()

    time.sleep(0.1)

  vessel.control.throttle = 0

def circularize(conn, vessel):
  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
  vessel.auto_pilot.target_direction = (0, 1, 0)

  while TLM.read("altitude") < 70000:
    TLM.update("Waiting to circularize")
    time.sleep(0.1)

  conn.space_center.warp_to(
    TLM.read("ut") + vessel.orbit.time_to_apoapsis - 10
  )

  vessel.control.throttle = 1

  while TLM.read("periapsis") < 80000:
    TLM.update("Circularizing")

    current_stage = vessel.control.current_stage
    next_stage = current_stage - 1

    if vessel.available_thrust < 0.1:
      if stage_has_engine(vessel, next_stage):
        vessel.control.activate_next_stage()
      else:
        TLM.update("Orbit failed")
        vessel.control.throttle = 0
        time.sleep(3)
        return suborbital_landing()

    time.sleep(0.1)

  vessel.control.throttle = 0

########## Maneuvers
# TODO: Refactor a lot of this code into subfunctions, clean it up, etc
# TODO: Improving warping in general
def suborbital_landing():
    conn, vessel = safe_connect("Launch")
    if not conn: return

    # TODO: Implement telemetry here, probably needs a telemetry rework
    
    while vessel.control.current_stage > 0:
      vessel.control.activate_next_stage()
    vessel.auto_pilot.reference_frame =  vessel.orbital_reference_frame
    vessel.auto_pilot.target_direction = (0, -1, 0)

def launch_to_orbit():
  conn, vessel = safe_connect("Launch")
  if not conn:
    return

  TLM.begin(conn, vessel)

  launch(conn, vessel)
  gravity_turn_to_orbit(conn, vessel)
  circularize(conn, vessel)

  TLM.update("Orbit achieved!")
  conn.close()

def land_rocket():
  conn, vessel = safe_connect("Land")
  if not conn:
    return

  TLM.begin(conn, vessel)

  TLM.update("Preparing deorbit burn")

  vessel.auto_pilot.engage()
  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame

  conn.space_center.warp_to(
    TLM.read("ut") + TLM.read("time_to_apoapsis")
  )

  TLM.update("Pointing retrograde")
  vessel.auto_pilot.target_direction = (0, -1, 0)
  vessel.auto_pilot.wait()

  TLM.update("Lowering periapsis")
  vessel.control.throttle = 0.1

  while TLM.read("periapsis") > 55000:
    TLM.update("Lowering periapsis")
    time.sleep(0.1)

  vessel.control.throttle = 0.0

  TLM.update("Coasting to atmosphere")

  while TLM.read("altitude") > 60000:
    TLM.update("Coasting to atmosphere")
    time.sleep(0.1)

  TLM.update("Burning remaining fuel")
  vessel.auto_pilot.target_direction = (0, -1, 0)
  vessel.control.throttle = 1.0

  while TLM.read("liquid_fuel") > 0.1:
    TLM.update("Burning remaining fuel")

    if vessel.control.throttle < 1.0:
      vessel.control.throttle = 1.0

    time.sleep(0.1)

  vessel.control.throttle = 0.0

  TLM.update("Dumping engines")
  vessel.control.activate_next_stage()

  TLM.update("Waiting to deploy parachutes")

  while TLM.read("altitude") > 5000:
    TLM.update("Waiting to deploy parachutes")
    time.sleep(0.1)

  TLM.update("Deploying parachutes")
  vessel.control.activate_next_stage()

  while not vessel_is_down(vessel):
    TLM.update("Descending under parachutes")
    time.sleep(0.1)

  TLM.update("Landed")
  conn.close()

def lko_tourism():
  launch_to_orbit()
  wait_one_hour()
  land_rocket()
