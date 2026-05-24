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


def stop_warp(conn):
  conn.space_center.rails_warp_factor = 0
  conn.space_center.physics_warp_factor = 0


def get_current_warp_factor(conn):
  return max(
    conn.space_center.rails_warp_factor,
    conn.space_center.physics_warp_factor,
  )


def manual_rails_warp_until(
  conn,
  status,
  stop_condition,
  warp_factor=5,
  update_interval=0.1,
  abort_condition=None,
):
  max_warp = conn.space_center.maximum_rails_warp_factor
  selected_warp = min(warp_factor, max_warp)

  if abort_condition is None:
    abort_condition = lambda: False

  try:
    while not stop_condition() and not abort_condition():
      TLM.update(status)

      if selected_warp > 0 and get_current_warp_factor(conn) <= 0:
        try:
          conn.space_center.rails_warp_factor = selected_warp
        except Exception:
          pass

      time.sleep(update_interval)

  finally:
    stop_warp(conn)


def wait_one_hour():
  conn, vessel = safe_connect("Wait")
  if not conn:
    return

  TLM.begin(conn, vessel)

  target_ut = TLM.read("ut") + 60 * 60

  manual_rails_warp_until(
    conn,
    "Warping for one hour",
    lambda: TLM.read("ut") >= target_ut,
    warp_factor=5,
  )

  TLM.update("One hour elapsed")
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
  time.sleep(1)

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

# TODO: Fix this warp and autopilot mess
def circularize(conn, vessel):
  while TLM.read("altitude") < 70000:
    TLM.update("Waiting to circularize")
    time.sleep(0.001)

  vessel.auto_pilot.target_direction = (0, 1, 0)
  vessel.auto_pilot.disengage()

  circularization_start_ut = (
    TLM.read("ut") +
    vessel.orbit.time_to_apoapsis -
    10
  )

  # manual_rails_warp_until(
  #   conn,
  #   "Warping to circularization",
  #   lambda: TLM.read("ut") >= circularization_start_ut,
  #   warp_factor=2,
  # )

  time.sleep(0.5)
  print("Beginning to aim prograde")
  vessel.auto_pilot.target_direction = (0, 1, 0)
  vessel.auto_pilot.engage()
  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
  # while vessel.auto_pilot.error > 1: time.sleep(0.001)
  # vessel.auto_pilot.wait()
  while TLM.read("ut") < circularization_start_ut:
    TLM.update("Waiting to Circularize")
    time.sleep(0.01)
  vessel.control.throttle = 1

  while TLM.read("periapsis") < 77500:
    TLM.update("Circularizing")

    current_stage = vessel.control.current_stage
    next_stage = current_stage - 1

    if vessel.available_thrust < 0.1:
      if stage_has_engine(vessel, next_stage):
        vessel.control.activate_next_stage()
      elif TLM.read("periapsis") < 70000:
        TLM.update("Orbit failed")
        vessel.control.throttle = 0
        time.sleep(3)
        return suborbital_landing()

    time.sleep(0.001)

  vessel.control.throttle = 0

########## Maneuvers
def suborbital_landing():
  conn, vessel = safe_connect("Launch")
  if not conn: return

  TLM.begin(conn, vessel)
  TLM.update("Preparing suborbital landing")

  while vessel.control.current_stage > 0:
    TLM.update("Dumping remaining stages")
    vessel.control.activate_next_stage()
    time.sleep(0.1)

  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
  vessel.auto_pilot.target_direction = (0, -1, 0)

  TLM.update("Suborbital landing configured")


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

  atmosphere_altitude = 70000
  deorbit_periapsis = 55000

  TLM.update("Preparing deorbit burn")

  vessel.auto_pilot.engage()
  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame

  apoapsis_arrival_ut = TLM.read("ut") + TLM.read("time_to_apoapsis")

  manual_rails_warp_until(
    conn,
    "Warping to apoapsis",
    lambda: TLM.read("ut") >= apoapsis_arrival_ut,
    warp_factor=5,
  )

  TLM.update("Pointing retrograde")
  vessel.auto_pilot.target_direction = (0, -1, 0)
  vessel.auto_pilot.wait()

  TLM.update("Lowering periapsis")
  vessel.control.throttle = 0.1

  while TLM.read("periapsis") > deorbit_periapsis:
    TLM.update("Lowering periapsis")
    time.sleep(0.1)

  vessel.control.throttle = 0.0

  manual_rails_warp_until(
    conn,
    "Warping to atmosphere",
    lambda: TLM.read("altitude") <= atmosphere_altitude,
    warp_factor=5,
    abort_condition=lambda: TLM.read("altitude") <= atmosphere_altitude,
  )

  TLM.update("Entering atmosphere")

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

  while TLM.read("altitude") > 5000:
    TLM.update("Waiting to deploy parachutes")
    time.sleep(0.1)

  TLM.update("Deploying parachutes")
  vessel.control.activate_next_stage()

  while not vessel_is_down(vessel):
    TLM.update("Descending under parachutes")
    time.sleep(0.1)

  TLM.update("Landed")
  stop_warp(conn)
  conn.close()


def lko_tourism():
  launch_to_orbit()
  wait_one_hour()
  land_rocket()
