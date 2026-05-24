import math
import time

from krpc_utils import safe_connect, stop_warp
from mission_state import (
  MissionAborted,
  MissionGuard,
  close_mission_connection,
  is_vessel_lost_error,
  mission_aborted_message,
  register_mission_connection,
)
from telemetry import TLM

########## Helpers

LAUNCH_VERTICAL_ASCENT_ALTITUDE = 1000
LAUNCH_TARGET_APOAPSIS = 80000
CIRCULARIZATION_ATMOSPHERE_ALTITUDE = 70000
CIRCULARIZATION_TARGET_PERIAPSIS = 77500
LANDING_ATMOSPHERE_ALTITUDE = 70000
LANDING_DEORBIT_PERIAPSIS = 55000
PARACHUTE_DEPLOY_ALTITUDE = 5000

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
  guard=None,
):
  max_warp = conn.space_center.maximum_rails_warp_factor
  selected_warp = min(warp_factor, max_warp)

  if abort_condition is None:
    abort_condition = lambda: False

  try:
    while not stop_condition() and not abort_condition():
      if guard:
        guard.check()

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
    raise MissionAborted("Wait stopped because no active vessel is available")

  register_mission_connection(conn, vessel, "Wait")
  guard = MissionGuard(conn, vessel, "Wait")

  try:
    guard.check(force=True)
    TLM.begin(conn, vessel)

    target_ut = TLM.read("ut") + 60 * 60

    manual_rails_warp_until(
      conn,
      "Warping for one hour",
      lambda: TLM.read("ut") >= target_ut,
      warp_factor=5,
      guard=guard,
    )

    TLM.update("One hour elapsed")
  except Exception as error:
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Wait")) from error
    raise
  finally:
    close_mission_connection(conn)


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

def launch(conn, vessel, guard):
  guard.check(force=True)
  TLM.update("Pre-flight check")
  vessel.control.sas = False
  vessel.control.rcs = False
  vessel.control.throttle = 1.0

  for status in ("Pre-flight check", "Launching in 3...", "Launching in 2...", "Launching in 1..."):
    TLM.update(status)
    time.sleep(1)
    guard.check(force=True)

  vessel.control.activate_next_stage()
  guard.check(force=True)
  vessel.auto_pilot.engage()
  vessel.auto_pilot.target_pitch_and_heading(90, 90)
  vessel.auto_pilot.target_roll = 0

  while TLM.read("altitude") < LAUNCH_VERTICAL_ASCENT_ALTITUDE:
    guard.check()
    TLM.update("Vertical Ascent")
    time.sleep(0.1)


def gravity_turn_to_orbit(conn, vessel, guard):
  guard.check(force=True)
  TLM.update("Pitch over")
  vessel.auto_pilot.target_pitch_and_heading(75, 90)

  for _ in range(70):
    time.sleep(0.1)
    guard.check()

  vessel.auto_pilot.reference_frame = vessel.surface_velocity_reference_frame
  vessel.auto_pilot.target_direction = (0, 1, 0)
  vessel.auto_pilot.target_roll = 0

  while TLM.read("apoapsis") < LAUNCH_TARGET_APOAPSIS:
    guard.check()
    TLM.update("Staging to space")

    current_stage = vessel.control.current_stage
    next_stage = current_stage - 1

    if vessel.available_thrust < 0.1 and stage_has_engine(vessel, next_stage):
      vessel.control.activate_next_stage()

    time.sleep(0.1)

  vessel.control.throttle = 0

def circularize(conn, vessel, guard):
  guard.check(force=True)
  while TLM.read("altitude") < CIRCULARIZATION_ATMOSPHERE_ALTITUDE:
    guard.check()
    TLM.update("Waiting to circularize")
    time.sleep(0.01)

  guard.check(force=True)
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
  guard.check(force=True)
  TLM.update("Aiming prograde")
  vessel.auto_pilot.target_direction = (0, 1, 0)
  vessel.auto_pilot.engage()
  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
  # while vessel.auto_pilot.error > 1: time.sleep(0.001)
  # vessel.auto_pilot.wait()
  while TLM.read("ut") < circularization_start_ut:
    guard.check()
    TLM.update("Waiting to Circularize")
    time.sleep(0.01)
  guard.check(force=True)
  vessel.control.throttle = 1

  while TLM.read("periapsis") < CIRCULARIZATION_TARGET_PERIAPSIS:
    guard.check()
    TLM.update("Circularizing")

    current_stage = vessel.control.current_stage
    next_stage = current_stage - 1

    if vessel.available_thrust < 0.1:
      if stage_has_engine(vessel, next_stage):
        vessel.control.activate_next_stage()
      elif TLM.read("periapsis") < CIRCULARIZATION_ATMOSPHERE_ALTITUDE:
        TLM.update("Orbit failed")
        vessel.control.throttle = 0
        for _ in range(30):
          time.sleep(0.1)
          guard.check()
        return suborbital_landing()

    time.sleep(0.01)

  guard.check(force=True)
  vessel.control.throttle = 0

########## Maneuvers
def suborbital_landing():
  conn, vessel = safe_connect("Launch")
  if not conn:
    raise MissionAborted("Suborbital landing stopped because no active vessel is available")

  register_mission_connection(conn, vessel, "Suborbital landing")
  guard = MissionGuard(conn, vessel, "Suborbital landing")

  try:
    guard.check(force=True)
    TLM.begin(conn, vessel)
    TLM.update("Preparing suborbital landing")

    while vessel.control.current_stage > 0:
      guard.check()
      TLM.update("Dumping remaining stages")
      vessel.control.activate_next_stage()
      time.sleep(0.1)

    guard.check(force=True)
    vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
    vessel.auto_pilot.target_direction = (0, -1, 0)

    TLM.update("Suborbital landing configured")
  except Exception as error:
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Suborbital landing")) from error
    raise
  finally:
    close_mission_connection(conn)


def launch_to_orbit():
  conn, vessel = safe_connect("Launch")
  if not conn:
    raise MissionAborted("Launch stopped because no active vessel is available")

  register_mission_connection(conn, vessel, "Launch")
  guard = MissionGuard(conn, vessel, "Launch")

  try:
    guard.check(force=True)
    TLM.begin(conn, vessel)

    launch(conn, vessel, guard)
    gravity_turn_to_orbit(conn, vessel, guard)
    circularize(conn, vessel, guard)

    TLM.update("Orbit achieved!")
  except Exception as error:
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Launch")) from error
    raise
  finally:
    close_mission_connection(conn)


def land_rocket():
  conn, vessel = safe_connect("Land")
  if not conn:
    raise MissionAborted("Land stopped because no active vessel is available")

  register_mission_connection(conn, vessel, "Land")
  guard = MissionGuard(conn, vessel, "Land")

  try:
    guard.check(force=True)
    TLM.begin(conn, vessel)

    TLM.update("Preparing deorbit burn")

    vessel.auto_pilot.engage()
    vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame

    apoapsis_arrival_ut = TLM.read("ut") + TLM.read("time_to_apoapsis")

    manual_rails_warp_until(
      conn,
      "Warping to apoapsis",
      lambda: TLM.read("ut") >= apoapsis_arrival_ut,
      warp_factor=5,
      guard=guard,
    )

    guard.check(force=True)
    TLM.update("Pointing retrograde")
    vessel.auto_pilot.target_direction = (0, -1, 0)
    vessel.auto_pilot.wait()

    TLM.update("Lowering periapsis")
    vessel.control.throttle = 0.1

    while TLM.read("periapsis") > LANDING_DEORBIT_PERIAPSIS:
      guard.check()
      TLM.update("Lowering periapsis")
      time.sleep(0.1)

    guard.check(force=True)
    vessel.control.throttle = 0.0

    manual_rails_warp_until(
      conn,
      "Warping to atmosphere",
      lambda: TLM.read("altitude") <= LANDING_ATMOSPHERE_ALTITUDE,
      warp_factor=5,
      abort_condition=lambda: TLM.read("altitude") <= LANDING_ATMOSPHERE_ALTITUDE,
      guard=guard,
    )

    TLM.update("Entering atmosphere")

    TLM.update("Burning remaining fuel")
    vessel.auto_pilot.target_direction = (0, -1, 0)
    vessel.control.throttle = 1.0

    while TLM.read("liquid_fuel") > 0.1:
      guard.check()
      TLM.update("Burning remaining fuel")

      if vessel.control.throttle < 1.0:
        vessel.control.throttle = 1.0

      time.sleep(0.1)

    guard.check(force=True)
    vessel.control.throttle = 0.0

    TLM.update("Dumping engines")
    vessel.control.activate_next_stage()

    while TLM.read("altitude") > PARACHUTE_DEPLOY_ALTITUDE:
      guard.check()
      TLM.update("Waiting to deploy parachutes")
      time.sleep(0.1)

    guard.check(force=True)
    TLM.update("Deploying parachutes")
    vessel.control.activate_next_stage()

    while not vessel_is_down(vessel):
      guard.check()
      TLM.update("Descending under parachutes")
      time.sleep(0.1)

    TLM.update("Landed")
  except Exception as error:
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Land")) from error
    raise
  finally:
    close_mission_connection(conn)


def lko_tourism():
  launch_to_orbit()
  wait_one_hour()
  land_rocket()
