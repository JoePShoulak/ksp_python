import math
import time

from krpc_utils import safe_connect, stop_warp
from mission_state import (
  MissionAborted,
  MissionGuard,
  close_mission_connection,
  is_vessel_lost_error,
  mission_aborted_message,
  record_mission_event,
  register_mission_connection,
)
from telemetry import TLM

########## Helpers

LAUNCH_VERTICAL_ASCENT_ALTITUDE = 1000
LAUNCH_VERTICAL_ASCENT_TIMEOUT = 45
LAUNCH_MIN_CLIMB_ALTITUDE = 120
LAUNCH_TARGET_APOAPSIS = 80000
CIRCULARIZATION_ATMOSPHERE_ALTITUDE = 70000
CIRCULARIZATION_TOURISM_PERIAPSIS = 75000
CIRCULARIZATION_LEAD_TIME = 10
CIRCULARIZATION_ALIGNMENT_BUFFER = 75
CIRCULARIZATION_TARGET_PERIAPSIS = 75100
CIRCULARIZATION_TARGET_APOAPSIS = 82000
CIRCULARIZATION_SOFT_APOAPSIS_LIMIT = 90000
CIRCULARIZATION_HARD_APOAPSIS_LIMIT = 110000
CIRCULARIZATION_ABORT_APOAPSIS_LIMIT = 125000
CIRCULARIZATION_MIN_BURN_TIME = 0.25
CIRCULARIZATION_MAX_BURN_TIME = 90
CIRCULARIZATION_TIME_TO_APOAPSIS_TARGET = 25
CIRCULARIZATION_TIME_TO_APOAPSIS_BAND = 3
CIRCULARIZATION_TIME_TO_APOAPSIS_SLOPE = 18
CIRCULARIZATION_TIME_TO_APOAPSIS_MIN_THROTTLE = 0.05
CIRCULARIZATION_TIME_TO_APOAPSIS_MAX_THROTTLE = 1
CIRCULARIZATION_MISSED_APOAPSIS_THRESHOLD = 300
CIRCULARIZATION_FINE_TRIM_PERIAPSIS = 70000
CIRCULARIZATION_SLOW_TRIM_PERIAPSIS = 50000
CIRCULARIZATION_MEDIUM_TRIM_PERIAPSIS = 0
CIRCULARIZATION_COARSE_TRIM_PERIAPSIS = -50000
CIRCULARIZATION_FINE_TRIM_THROTTLE = 0.08
CIRCULARIZATION_SLOW_TRIM_THROTTLE = 0.15
CIRCULARIZATION_MEDIUM_TRIM_THROTTLE = 0.3
CIRCULARIZATION_COARSE_TRIM_THROTTLE = 0.6
CIRCULARIZATION_SOFT_TRIM_PERIAPSIS_REMAINING = 1200
CIRCULARIZATION_SOFT_TRIM_THROTTLE = 0.05
CIRCULARIZATION_LATE_TRIM_THROTTLE = 0.08
LANDING_ATMOSPHERE_ALTITUDE = 70000
LANDING_DEORBIT_PERIAPSIS = 55000
LANDING_DEORBIT_ALIGNMENT_BUFFER = 75
LANDING_DEORBIT_BURN_LEAD_TIME = 5
LANDING_DEORBIT_THROTTLE = 0.1
LANDING_DEORBIT_DRIFT_ERROR = 5
PARACHUTE_DEPLOY_ALTITUDE = 5000
DESCENT_PHYSICS_WARP_FACTOR = 3
ASCENT_PHYSICS_WARP_FACTOR = 3
RAILS_WARP_FACTOR = 7
AUTOPILOT_ALIGNMENT_ERROR = 2
AUTOPILOT_ALIGNMENT_TIMEOUT = 10
CIRCULARIZATION_BURN_INTERVAL = 0.002

def get_current_warp_factor(conn):
  return max(
    conn.space_center.rails_warp_factor,
    conn.space_center.physics_warp_factor,
  )


def set_physics_warp(conn, warp_factor):
  try:
    if conn.space_center.rails_warp_factor > 0:
      conn.space_center.rails_warp_factor = 0

    if conn.space_center.physics_warp_factor != warp_factor:
      conn.space_center.physics_warp_factor = warp_factor
  except Exception:
    pass


def set_rails_warp(conn, warp_factor):
  try:
    if conn.space_center.physics_warp_factor > 0:
      conn.space_center.physics_warp_factor = 0

    if conn.space_center.rails_warp_factor != warp_factor:
      conn.space_center.rails_warp_factor = warp_factor
  except Exception:
    pass


def wait_for_autopilot_alignment(vessel, guard, status, max_wait=AUTOPILOT_ALIGNMENT_TIMEOUT):
  started_at = time.monotonic()

  while time.monotonic() - started_at < max_wait:
    guard.check()
    TLM.update(status)

    try:
      if vessel.auto_pilot.error <= AUTOPILOT_ALIGNMENT_ERROR:
        return True
    except Exception:
      return False

    time.sleep(0.1)

  return False


def read_autopilot_error(vessel):
  try:
    return vessel.auto_pilot.error
  except Exception:
    return None


def reset_manual_controls(vessel):
  vessel.control.throttle = 0
  vessel.control.pitch = 0
  vessel.control.yaw = 0
  vessel.control.roll = 0
  vessel.control.forward = 0
  vessel.control.right = 0
  vessel.control.up = 0


def manual_physics_warp_until(
  conn,
  status,
  stop_condition,
  warp_factor=DESCENT_PHYSICS_WARP_FACTOR,
  update_interval=0.1,
  abort_condition=None,
  guard=None,
):
  if abort_condition is None:
    abort_condition = lambda: False

  try:
    while not stop_condition() and not abort_condition():
      if guard:
        guard.check()

      TLM.update(status)

      set_physics_warp(conn, warp_factor)

      time.sleep(update_interval)

  finally:
    stop_warp(conn)


def maintain_physics_warp(conn, warp_factor=DESCENT_PHYSICS_WARP_FACTOR):
  if warp_factor <= 0:
    return

  set_physics_warp(conn, warp_factor)


def manual_rails_warp_until(
  conn,
  status,
  stop_condition,
  warp_factor=5,
  update_interval=0.1,
  abort_condition=None,
  guard=None,
  allow_physics_fallback=False,
  physics_fallback_after=1.0,
):
  max_warp = conn.space_center.maximum_rails_warp_factor
  selected_warp = min(warp_factor, max_warp)
  fallback_pending_since = None
  use_physics_fallback = False
  fallback_reported = False

  if abort_condition is None:
    abort_condition = lambda: False

  try:
    while not stop_condition() and not abort_condition():
      if guard:
        guard.check()

      TLM.update(status)

      if use_physics_fallback:
        set_physics_warp(conn, DESCENT_PHYSICS_WARP_FACTOR)
      else:
        set_rails_warp(conn, selected_warp)

        if allow_physics_fallback and get_current_warp_factor(conn) <= 1:
          if fallback_pending_since is None:
            fallback_pending_since = time.monotonic()
          elif time.monotonic() - fallback_pending_since >= physics_fallback_after:
            use_physics_fallback = True
            if not fallback_reported:
              record_mission_event(
                "rails_warp_fallback_to_physics",
                None,
                status=status,
                target_warp=selected_warp,
              )
              fallback_reported = True
            set_physics_warp(conn, DESCENT_PHYSICS_WARP_FACTOR)
        else:
          fallback_pending_since = None

      time.sleep(update_interval)

  finally:
    stop_warp(conn)


def coast_to_ut(conn, status, target_ut, warp_factor=RAILS_WARP_FACTOR, guard=None):
  target_ut = max(target_ut, TLM.read("ut"))

  if target_ut <= TLM.read("ut") + 0.5:
    return

  manual_rails_warp_until(
    conn,
    status,
    lambda: TLM.read("ut") >= target_ut,
    warp_factor=warp_factor,
    guard=guard,
    allow_physics_fallback=True,
  )


def warp_to_ut(conn, status, target_ut, warp_factor=RAILS_WARP_FACTOR, guard=None):
  if guard:
    guard.check(force=True)

  selected_warp = min(warp_factor, conn.space_center.maximum_rails_warp_factor)
  target_ut = max(target_ut, TLM.read("ut"))

  if target_ut <= TLM.read("ut") + 0.5:
    return

  TLM.update(status)

  try:
    try:
      conn.space_center.warp_to(
        target_ut,
        max_rails_warp_factor=selected_warp,
        max_physics_warp_factor=0,
      )
    except TypeError:
      conn.space_center.warp_to(target_ut, selected_warp, 0)
  finally:
    stop_warp(conn)

  if guard:
    guard.check(force=True)

  TLM.update(status)


def rails_warp_toward_periapsis(conn, status, guard, lead_time=45):
  while TLM.read("time_to_periapsis") > lead_time:
    guard.check()
    coast_time = min(TLM.read("time_to_periapsis") - lead_time, 300)
    target_ut = TLM.read("ut") + max(1, coast_time)
    coast_to_ut(conn, status, target_ut, guard=guard)


def rails_warp_to_atmosphere(conn, status, guard, update_interval=0.1):
  try:
    while TLM.read("altitude") > LANDING_ATMOSPHERE_ALTITUDE:
      guard.check()
      TLM.update(status)
      set_rails_warp(conn, RAILS_WARP_FACTOR)
      time.sleep(update_interval)
  finally:
    stop_warp(conn)


def get_circularization_periapsis_throttle(periapsis):
  if periapsis >= CIRCULARIZATION_FINE_TRIM_PERIAPSIS:
    return CIRCULARIZATION_FINE_TRIM_THROTTLE

  if periapsis >= CIRCULARIZATION_SLOW_TRIM_PERIAPSIS:
    return CIRCULARIZATION_SLOW_TRIM_THROTTLE

  if periapsis >= CIRCULARIZATION_MEDIUM_TRIM_PERIAPSIS:
    return CIRCULARIZATION_MEDIUM_TRIM_THROTTLE

  if periapsis >= CIRCULARIZATION_COARSE_TRIM_PERIAPSIS:
    return CIRCULARIZATION_COARSE_TRIM_THROTTLE

  return 1


def set_circularization_throttle(vessel):
  periapsis = TLM.read("periapsis")
  apoapsis = TLM.read("apoapsis")
  time_to_apoapsis = TLM.read("time_to_apoapsis")

  if apoapsis >= CIRCULARIZATION_ABORT_APOAPSIS_LIMIT:
    vessel.control.throttle = 0
    return

  if (
    apoapsis >= CIRCULARIZATION_HARD_APOAPSIS_LIMIT and
    periapsis >= CIRCULARIZATION_TARGET_PERIAPSIS
  ):
    vessel.control.throttle = 0
    return

  if periapsis >= CIRCULARIZATION_TARGET_PERIAPSIS:
    vessel.control.throttle = 0
    return

  periapsis_throttle = get_circularization_periapsis_throttle(periapsis)

  if time_to_apoapsis > CIRCULARIZATION_MISSED_APOAPSIS_THRESHOLD:
    if periapsis < CIRCULARIZATION_MEDIUM_TRIM_PERIAPSIS:
      vessel.control.throttle = periapsis_throttle
      return

    vessel.control.throttle = min(
      CIRCULARIZATION_MEDIUM_TRIM_THROTTLE,
      periapsis_throttle,
    )
    return

  time_error = CIRCULARIZATION_TIME_TO_APOAPSIS_TARGET - time_to_apoapsis
  time_throttle = (
    CIRCULARIZATION_TIME_TO_APOAPSIS_MIN_THROTTLE +
    max(0, time_error + CIRCULARIZATION_TIME_TO_APOAPSIS_BAND) /
    CIRCULARIZATION_TIME_TO_APOAPSIS_SLOPE
  )
  time_throttle = min(
    CIRCULARIZATION_TIME_TO_APOAPSIS_MAX_THROTTLE,
    max(CIRCULARIZATION_TIME_TO_APOAPSIS_MIN_THROTTLE, time_throttle),
  )

  vessel.control.throttle = min(periapsis_throttle, time_throttle)


def calculate_orbital_speed(mu, radius, semi_major_axis):
  return math.sqrt(mu * ((2 / radius) - (1 / semi_major_axis)))


def calculate_apsis_burn_delta_v(vessel):
  try:
    body = vessel.orbit.body
    mu = body.gravitational_parameter
    body_radius = body.equatorial_radius
    apoapsis_radius = body_radius + max(
      TLM.read("apoapsis"),
      CIRCULARIZATION_TARGET_APOAPSIS,
    )
    current_periapsis_radius = max(
      1,
      body_radius + TLM.read("periapsis"),
    )
    target_periapsis_radius = body_radius + CIRCULARIZATION_TARGET_PERIAPSIS
    current_semi_major_axis = (apoapsis_radius + current_periapsis_radius) / 2
    target_semi_major_axis = (apoapsis_radius + target_periapsis_radius) / 2
    current_apoapsis_speed = calculate_orbital_speed(
      mu,
      apoapsis_radius,
      current_semi_major_axis,
    )
    target_apoapsis_speed = calculate_orbital_speed(
      mu,
      apoapsis_radius,
      target_semi_major_axis,
    )

    return max(0, target_apoapsis_speed - current_apoapsis_speed)
  except Exception:
    return 0


def estimate_burn_acceleration(vessel):
  try:
    return vessel.available_thrust / max(vessel.mass, 1)
  except Exception:
    return 0


def plan_circularization_burn(vessel):
  delta_v = calculate_apsis_burn_delta_v(vessel)
  acceleration = estimate_burn_acceleration(vessel)

  if acceleration <= 0:
    full_throttle_burn_time = CIRCULARIZATION_LEAD_TIME * 2
  else:
    full_throttle_burn_time = delta_v / acceleration

  full_throttle_burn_time = min(
    CIRCULARIZATION_MAX_BURN_TIME,
    max(CIRCULARIZATION_MIN_BURN_TIME, full_throttle_burn_time),
  )
  return {
    "delta_v": delta_v,
    "acceleration": acceleration,
    "full_throttle_burn_time": full_throttle_burn_time,
    "burn_time": full_throttle_burn_time,
    "lead_time": CIRCULARIZATION_TIME_TO_APOAPSIS_TARGET,
  }


def should_cut_circularization_burn(ut, apoapsis_ut):
  periapsis = TLM.read("periapsis")
  apoapsis = TLM.read("apoapsis")

  if apoapsis >= CIRCULARIZATION_ABORT_APOAPSIS_LIMIT:
    return "circularization_abort_apoapsis_cutoff"

  if (
    ut >= apoapsis_ut and
    periapsis >= CIRCULARIZATION_TOURISM_PERIAPSIS
  ):
    return "circularization_apoapsis_window_cutoff"

  if (
    apoapsis >= CIRCULARIZATION_HARD_APOAPSIS_LIMIT and
    periapsis >= CIRCULARIZATION_TARGET_PERIAPSIS
  ):
    return "circularization_apoapsis_cutoff"

  return None


def configure_suborbital_landing(conn, vessel, guard, dump_stages=False):
  TLM.update("Preparing suborbital landing")
  stop_warp(conn)
  vessel.control.throttle = 0

  if dump_stages:
    while vessel.control.current_stage > 0:
      guard.check()
      vessel.control.throttle = 0
      TLM.update("Dumping remaining stages")
      vessel.control.activate_next_stage()
      time.sleep(0.1)

  guard.check(force=True)
  vessel.auto_pilot.engage()
  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
  vessel.auto_pilot.target_direction = (0, -1, 0)
  TLM.update("Suborbital landing configured")


def wait_one_hour():
  record_mission_event("wait_enter", "Wait")
  conn, vessel = safe_connect("Wait")
  if not conn:
    record_mission_event("wait_no_connection", "Wait")
    raise MissionAborted("Wait stopped because no active vessel is available")

  record_mission_event("wait_connected", "Wait")
  register_mission_connection(conn, vessel, "Wait")
  guard = MissionGuard(conn, vessel, "Wait")

  try:
    record_mission_event("wait_guard_check_start", "Wait")
    guard.check(force=True)
    record_mission_event("wait_tlm_begin_start", "Wait")
    TLM.begin(conn, vessel)
    record_mission_event("wait_tlm_begin_done", "Wait")

    if TLM.read("periapsis") < CIRCULARIZATION_TOURISM_PERIAPSIS:
      record_mission_event(
        "wait_unstable_orbit",
        "Wait",
        periapsis=TLM.read("periapsis"),
        minimum_periapsis=CIRCULARIZATION_TOURISM_PERIAPSIS,
      )
      raise MissionAborted("Wait stopped because the vessel is not in a tourism orbit")

    target_ut = TLM.read("ut") + 60 * 60
    record_mission_event("wait_warp_start", "Wait", target_ut=target_ut)

    manual_rails_warp_until(
      conn,
      "Warping for one hour",
      lambda: TLM.read("ut") >= target_ut,
      warp_factor=RAILS_WARP_FACTOR,
      guard=guard,
    )

    record_mission_event("wait_warp_done", "Wait")
    TLM.update("One hour elapsed")
  except Exception as error:
    record_mission_event("wait_error", "Wait", error=str(error))
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Wait")) from error
    raise
  finally:
    record_mission_event("wait_close", "Wait")
    close_mission_connection(conn)


def vessel_is_down(vessel):
  return vessel.situation in (
    vessel.situation.landed,
    vessel.situation.splashed,
  )


def has_usable_thrust(vessel):
  return TLM.read("liquid_fuel") > 0.1 and vessel.available_thrust > 0.1


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


def burn_remaining_fuel_for_descent(conn, vessel, guard):
  if not has_usable_thrust(vessel):
    return

  TLM.update("Burning remaining fuel")
  vessel.auto_pilot.target_direction = (0, -1, 0)
  vessel.control.throttle = 1.0

  while has_usable_thrust(vessel):
    guard.check()
    maintain_physics_warp(conn)
    TLM.update("Burning remaining fuel")

    if vessel.control.throttle < 1.0:
      vessel.control.throttle = 1.0

    time.sleep(0.1)

  guard.check(force=True)
  vessel.control.throttle = 0.0


def warp_physics_through_atmosphere(conn, vessel, guard, parachutes_deployed):
  TLM.update("Aerobraking")
  maintain_physics_warp(conn)

  while not vessel_is_down(vessel):
    guard.check()
    maintain_physics_warp(conn)

    if TLM.read("altitude") <= PARACHUTE_DEPLOY_ALTITUDE and not parachutes_deployed:
      TLM.update("Deploying parachutes")
      stop_warp(conn)
      vessel.control.activate_next_stage()
      parachutes_deployed = True

    if parachutes_deployed:
      TLM.update("Descending under parachutes")
    else:
      TLM.update("Aerobraking")

    if (
      TLM.read("altitude") > LANDING_ATMOSPHERE_ALTITUDE and
      TLM.read("vertical_speed") > 0
    ):
      stop_warp(conn)
      return parachutes_deployed

    time.sleep(0.1)

  return parachutes_deployed


def warp_through_aerobraking(conn, vessel, guard):
  engines_dropped = False
  parachutes_deployed = False

  while not vessel_is_down(vessel):
    guard.check()

    if TLM.read("altitude") > LANDING_ATMOSPHERE_ALTITUDE:
      rails_warp_to_atmosphere(conn, "Rails warping to atmosphere", guard)

    if vessel_is_down(vessel):
      break

    TLM.update("Entering atmosphere")
    maintain_physics_warp(conn)

    if not engines_dropped:
      burn_remaining_fuel_for_descent(conn, vessel, guard)
      TLM.update("Dumping engines")
      vessel.control.activate_next_stage()
      engines_dropped = True

    parachutes_deployed = warp_physics_through_atmosphere(
      conn,
      vessel,
      guard,
      parachutes_deployed,
    )

  TLM.update("Landed")
  stop_warp(conn)

########## Mini-Maneuvers

def launch(conn, vessel, guard):
  guard.check(force=True)
  TLM.update("Pre-flight check")
  stop_warp(conn)
  reset_manual_controls(vessel)
  vessel.auto_pilot.engage()
  vessel.auto_pilot.target_pitch_and_heading(90, 90)
  vessel.auto_pilot.target_roll = 0
  vessel.control.sas = False
  vessel.control.rcs = False

  record_mission_event(
    "launch_vertical_guidance_armed",
    "Launch",
    autopilot_error=read_autopilot_error(vessel),
  )

  for status in ("Pre-flight check", "Launching in 3...", "Launching in 2...", "Launching in 1..."):
    TLM.update(status)
    time.sleep(1)
    guard.check(force=True)

  vessel.control.throttle = 1.0
  vessel.control.activate_next_stage()
  guard.check(force=True)

  ascent_started_at = time.monotonic()
  while TLM.read("altitude") < LAUNCH_VERTICAL_ASCENT_ALTITUDE:
    guard.check()
    TLM.update("Vertical Ascent")

    if (
      time.monotonic() - ascent_started_at > LAUNCH_VERTICAL_ASCENT_TIMEOUT or
      (
        time.monotonic() - ascent_started_at > 8 and
        TLM.read("altitude") < LAUNCH_MIN_CLIMB_ALTITUDE
      )
    ):
      vessel.control.throttle = 0
      record_mission_event(
        "launch_vertical_ascent_failed",
        "Launch",
        altitude=TLM.read("altitude"),
        vertical_speed=TLM.read("vertical_speed"),
        apoapsis=TLM.read("apoapsis"),
        periapsis=TLM.read("periapsis"),
      )
      raise MissionAborted("Launch stopped because the vessel did not climb cleanly")

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

  manual_physics_warp_until(
    conn,
    "Physics warping to atmosphere edge",
    lambda: (
      TLM.read("altitude") >= CIRCULARIZATION_ATMOSPHERE_ALTITUDE or
      TLM.read("time_to_apoapsis") <=
      CIRCULARIZATION_LEAD_TIME + CIRCULARIZATION_ALIGNMENT_BUFFER
    ),
    warp_factor=ASCENT_PHYSICS_WARP_FACTOR,
    guard=guard,
  )

  guard.check(force=True)
  TLM.update("Aiming prograde")
  vessel.auto_pilot.engage()
  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
  vessel.auto_pilot.target_direction = (0, 1, 0)
  vessel.auto_pilot.target_roll = 0

  circularization_plan = plan_circularization_burn(vessel)
  record_mission_event(
    "circularization_plan",
    "Launch",
    lead_time=circularization_plan["lead_time"],
    burn_time=circularization_plan["burn_time"],
    full_throttle_burn_time=circularization_plan["full_throttle_burn_time"],
    estimated_delta_v=circularization_plan["delta_v"],
    acceleration=circularization_plan["acceleration"],
    apoapsis=TLM.read("apoapsis"),
    periapsis=TLM.read("periapsis"),
    alignment_buffer=CIRCULARIZATION_ALIGNMENT_BUFFER,
  )

  circularization_start_ut = TLM.read("ut") + max(
    0,
    vessel.orbit.time_to_apoapsis - circularization_plan["lead_time"],
  )
  circularization_end_ut = (
    circularization_start_ut +
    circularization_plan["burn_time"]
  )
  circularization_apoapsis_ut = circularization_start_ut + circularization_plan["lead_time"]
  circularization_alignment_ut = max(
    TLM.read("ut"),
    circularization_start_ut - CIRCULARIZATION_ALIGNMENT_BUFFER,
  )

  if TLM.read("ut") < circularization_alignment_ut:
    coast_to_ut(
      conn,
      "Rails warping to alignment",
      circularization_alignment_ut,
      warp_factor=RAILS_WARP_FACTOR,
      guard=guard,
    )

  time.sleep(0.5)
  guard.check(force=True)
  stop_warp(conn)
  vessel.control.throttle = 0
  TLM.update("Aiming prograde")
  vessel.auto_pilot.engage()
  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
  vessel.auto_pilot.target_direction = (0, 1, 0)
  vessel.auto_pilot.target_roll = 0
  record_mission_event(
    "circularization_alignment_start",
    "Launch",
    autopilot_error=read_autopilot_error(vessel),
    time_to_apoapsis=TLM.read("time_to_apoapsis"),
  )

  if not wait_for_autopilot_alignment(vessel, guard, "Aiming prograde", max_wait=45):
    vessel.control.throttle = 0
    record_mission_event(
      "circularization_alignment_failed",
      "Launch",
      autopilot_error=read_autopilot_error(vessel),
      time_to_apoapsis=TLM.read("time_to_apoapsis"),
      apoapsis=TLM.read("apoapsis"),
      periapsis=TLM.read("periapsis"),
    )
    return False

  record_mission_event(
    "circularization_alignment_done",
    "Launch",
    autopilot_error=read_autopilot_error(vessel),
    time_to_apoapsis=TLM.read("time_to_apoapsis"),
  )

  while TLM.read("ut") < circularization_start_ut:
    guard.check()
    TLM.update("Waiting to Circularize")
    time.sleep(CIRCULARIZATION_BURN_INTERVAL)

  guard.check(force=True)
  soft_trim_recorded = False
  time_to_apoapsis_control_recorded = False

  while TLM.read("periapsis") < CIRCULARIZATION_TARGET_PERIAPSIS:
    guard.check()
    TLM.update("Circularizing")
    autopilot_error = read_autopilot_error(vessel)

    if autopilot_error is not None and autopilot_error > AUTOPILOT_ALIGNMENT_ERROR:
      vessel.control.throttle = 0
      record_mission_event(
        "circularization_alignment_lost",
        "Launch",
        autopilot_error=autopilot_error,
        apoapsis=TLM.read("apoapsis"),
        periapsis=TLM.read("periapsis"),
      )

      if not wait_for_autopilot_alignment(vessel, guard, "Reacquiring prograde", max_wait=10):
        return False

      vessel.control.throttle = 0

    time_remaining = max(0, circularization_end_ut - TLM.read("ut"))
    periapsis_remaining = max(0, CIRCULARIZATION_TARGET_PERIAPSIS - TLM.read("periapsis"))
    time_to_apoapsis = TLM.read("time_to_apoapsis")

    set_circularization_throttle(vessel)

    if not time_to_apoapsis_control_recorded:
      time_to_apoapsis_control_recorded = True
      record_mission_event(
        "circularization_time_to_apoapsis_control",
        "Launch",
        target_time_to_apoapsis=CIRCULARIZATION_TIME_TO_APOAPSIS_TARGET,
        time_to_apoapsis=time_to_apoapsis,
        throttle=vessel.control.throttle,
      )

    cutoff_event = should_cut_circularization_burn(
      TLM.read("ut"),
      circularization_apoapsis_ut,
    )

    if cutoff_event:
      record_mission_event(
        cutoff_event,
        "Launch",
        apoapsis=TLM.read("apoapsis"),
        periapsis=TLM.read("periapsis"),
        time_to_apoapsis=time_to_apoapsis,
        time_remaining=time_remaining,
      )
      break

    if (
      TLM.read("apoapsis") >= CIRCULARIZATION_SOFT_APOAPSIS_LIMIT and
      periapsis_remaining <= CIRCULARIZATION_SOFT_TRIM_PERIAPSIS_REMAINING
    ):
      vessel.control.throttle = min(
        vessel.control.throttle,
        CIRCULARIZATION_SOFT_TRIM_THROTTLE,
      )
      if not soft_trim_recorded:
        soft_trim_recorded = True
        record_mission_event(
          "circularization_soft_trim",
          "Launch",
          apoapsis=TLM.read("apoapsis"),
          periapsis=TLM.read("periapsis"),
          time_to_apoapsis=time_to_apoapsis,
          time_remaining=time_remaining,
        )

    current_stage = vessel.control.current_stage
    next_stage = current_stage - 1

    if vessel.available_thrust < 0.1:
      if stage_has_engine(vessel, next_stage):
        vessel.control.activate_next_stage()
      elif TLM.read("periapsis") < CIRCULARIZATION_ATMOSPHERE_ALTITUDE:
        TLM.update("Orbit failed")
        vessel.control.throttle = 0
        configure_suborbital_landing(conn, vessel, guard)
        return False

    time.sleep(CIRCULARIZATION_BURN_INTERVAL)

  guard.check(force=True)
  vessel.control.throttle = 0
  record_mission_event(
    "circularization_burn_done",
    "Launch",
    apoapsis=TLM.read("apoapsis"),
    periapsis=TLM.read("periapsis"),
    delta_v=TLM.read_delta_v(),
    planned_end_ut=circularization_end_ut,
    actual_ut=TLM.read("ut"),
  )

  return TLM.read("periapsis") >= CIRCULARIZATION_TOURISM_PERIAPSIS

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

    configure_suborbital_landing(conn, vessel, guard)
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
    if not circularize(conn, vessel, guard):
      record_mission_event(
        "launch_orbit_failed_descent_start",
        "Launch",
        apoapsis=TLM.read("apoapsis"),
        periapsis=TLM.read("periapsis"),
      )
      TLM.update("Orbit failed")
      configure_suborbital_landing(conn, vessel, guard)
      warp_through_aerobraking(conn, vessel, guard)
      record_mission_event("launch_orbit_failed_descent_done", "Launch")
      return False

    TLM.update("Orbit achieved!")
    return True
  except Exception as error:
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Launch")) from error
    raise
  finally:
    close_mission_connection(conn)


def land_rocket():
  record_mission_event("land_enter", "Land")
  conn, vessel = safe_connect("Land")
  if not conn:
    record_mission_event("land_no_connection", "Land")
    raise MissionAborted("Land stopped because no active vessel is available")

  record_mission_event("land_connected", "Land")
  register_mission_connection(conn, vessel, "Land")
  guard = MissionGuard(conn, vessel, "Land")

  try:
    record_mission_event("land_tlm_begin_start", "Land")
    TLM.begin(conn, vessel)
    record_mission_event("land_tlm_begin_done", "Land")
    TLM.update("Preparing deorbit burn")
    record_mission_event("land_guard_check_start", "Land")
    guard.check(force=True)
    record_mission_event("land_guard_check_done", "Land")

    record_mission_event("land_autopilot_setup_start", "Land")
    vessel.auto_pilot.engage()
    vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
    record_mission_event("land_autopilot_setup_done", "Land")

    apoapsis_arrival_ut = TLM.read("ut") + TLM.read("time_to_apoapsis")
    alignment_ut = max(
      TLM.read("ut"),
      apoapsis_arrival_ut - LANDING_DEORBIT_ALIGNMENT_BUFFER,
    )
    burn_start_ut = max(
      TLM.read("ut"),
      apoapsis_arrival_ut - LANDING_DEORBIT_BURN_LEAD_TIME,
    )
    record_mission_event(
      "land_warp_to_alignment_start",
      "Land",
      target_ut=apoapsis_arrival_ut,
      alignment_ut=alignment_ut,
      burn_start_ut=burn_start_ut,
      time_to_apoapsis=TLM.read("time_to_apoapsis"),
    )

    coast_to_ut(
      conn,
      "Warping to deorbit alignment",
      alignment_ut,
      warp_factor=RAILS_WARP_FACTOR,
      guard=guard,
    )

    record_mission_event(
      "land_warp_to_alignment_done",
      "Land",
      time_to_apoapsis=TLM.read("time_to_apoapsis"),
    )
    guard.check(force=True)
    TLM.update("Pointing retrograde")
    vessel.auto_pilot.engage()
    vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
    vessel.auto_pilot.target_direction = (0, -1, 0)
    vessel.auto_pilot.target_roll = 0
    record_mission_event("land_align_retrograde_start", "Land")
    if not wait_for_autopilot_alignment(vessel, guard, "Pointing retrograde", max_wait=45):
      record_mission_event(
        "land_align_retrograde_failed",
        "Land",
        autopilot_error=read_autopilot_error(vessel),
        time_to_apoapsis=TLM.read("time_to_apoapsis"),
        apoapsis=TLM.read("apoapsis"),
        periapsis=TLM.read("periapsis"),
      )
      raise MissionAborted("Land stopped because retrograde alignment did not settle")

    record_mission_event(
      "land_align_retrograde_done",
      "Land",
      autopilot_error=read_autopilot_error(vessel),
    )

    while TLM.read("ut") < burn_start_ut:
      guard.check()
      TLM.update("Waiting for deorbit burn")
      autopilot_error = read_autopilot_error(vessel)
      if autopilot_error is not None and autopilot_error > LANDING_DEORBIT_DRIFT_ERROR:
        record_mission_event(
          "land_align_retrograde_drifted_before_burn",
          "Land",
          autopilot_error=autopilot_error,
          time_to_apoapsis=TLM.read("time_to_apoapsis"),
        )
        if not wait_for_autopilot_alignment(vessel, guard, "Reacquiring retrograde", max_wait=10):
          raise MissionAborted("Land stopped because retrograde alignment was lost before deorbit burn")

      time.sleep(0.05)

    if not wait_for_autopilot_alignment(vessel, guard, "Final deorbit alignment", max_wait=5):
      record_mission_event(
        "land_final_align_retrograde_failed",
        "Land",
        autopilot_error=read_autopilot_error(vessel),
        time_to_apoapsis=TLM.read("time_to_apoapsis"),
        apoapsis=TLM.read("apoapsis"),
        periapsis=TLM.read("periapsis"),
      )
      raise MissionAborted("Land stopped because retrograde alignment was not ready at deorbit burn")

    TLM.update("Lowering periapsis")
    vessel.control.throttle = LANDING_DEORBIT_THROTTLE
    record_mission_event(
      "land_deorbit_burn_start",
      "Land",
      autopilot_error=read_autopilot_error(vessel),
      time_to_apoapsis=TLM.read("time_to_apoapsis"),
      apoapsis=TLM.read("apoapsis"),
      periapsis=TLM.read("periapsis"),
    )

    while TLM.read("periapsis") > LANDING_DEORBIT_PERIAPSIS:
      guard.check()
      TLM.update("Lowering periapsis")

      if read_autopilot_error(vessel) is not None and read_autopilot_error(vessel) > AUTOPILOT_ALIGNMENT_ERROR:
        vessel.control.throttle = 0
        record_mission_event(
          "land_align_retrograde_lost",
          "Land",
          autopilot_error=read_autopilot_error(vessel),
          apoapsis=TLM.read("apoapsis"),
          periapsis=TLM.read("periapsis"),
        )

        if not wait_for_autopilot_alignment(vessel, guard, "Reacquiring retrograde", max_wait=10):
          raise MissionAborted("Land stopped because retrograde alignment was lost")

        vessel.control.throttle = LANDING_DEORBIT_THROTTLE

      if not has_usable_thrust(vessel):
        if TLM.read("periapsis") <= LANDING_ATMOSPHERE_ALTITUDE:
          break

        raise MissionAborted("Land stopped because deorbit burn ran out of fuel")

      time.sleep(0.1)

    guard.check(force=True)
    vessel.control.throttle = 0.0
    record_mission_event("land_deorbit_burn_done", "Land", periapsis=TLM.read("periapsis"))

    warp_through_aerobraking(conn, vessel, guard)
  except Exception as error:
    record_mission_event("land_error", "Land", error=str(error))
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Land")) from error
    raise
  finally:
    record_mission_event("land_close", "Land")
    close_mission_connection(conn)


def lko_tourism():
  record_mission_event("lko_sequence_start", "lko_tourism")
  if not launch_to_orbit():
    record_mission_event("lko_sequence_orbit_failed", "lko_tourism")
    return

  record_mission_event("lko_sequence_wait_start", "lko_tourism")
  wait_one_hour()
  record_mission_event("lko_sequence_land_start", "lko_tourism")
  land_rocket()
  record_mission_event("lko_sequence_done", "lko_tourism")
