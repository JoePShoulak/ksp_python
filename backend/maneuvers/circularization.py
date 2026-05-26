import math
import time

from krpc_utils import stop_warp
from mission_state import record_mission_event
from telemetry import TLM

from .constants import (
  ASCENT_PHYSICS_WARP_FACTOR,
  AUTOPILOT_ALIGNMENT_ERROR,
  CIRCULARIZATION_ABORT_APOAPSIS_LIMIT,
  CIRCULARIZATION_ALIGNMENT_BUFFER,
  CIRCULARIZATION_ATMOSPHERE_ALTITUDE,
  CIRCULARIZATION_BURN_INTERVAL,
  CIRCULARIZATION_COARSE_TRIM_PERIAPSIS,
  CIRCULARIZATION_COARSE_TRIM_THROTTLE,
  CIRCULARIZATION_FINE_TRIM_PERIAPSIS,
  CIRCULARIZATION_FINE_TRIM_THROTTLE,
  CIRCULARIZATION_HARD_APOAPSIS_LIMIT,
  CIRCULARIZATION_LEAD_TIME,
  CIRCULARIZATION_MAX_BURN_TIME,
  CIRCULARIZATION_MEDIUM_TRIM_PERIAPSIS,
  CIRCULARIZATION_MEDIUM_TRIM_THROTTLE,
  CIRCULARIZATION_MIN_BURN_TIME,
  CIRCULARIZATION_MISSED_APOAPSIS_THRESHOLD,
  CIRCULARIZATION_SLOW_TRIM_PERIAPSIS,
  CIRCULARIZATION_SLOW_TRIM_THROTTLE,
  CIRCULARIZATION_SOFT_APOAPSIS_LIMIT,
  CIRCULARIZATION_SOFT_TRIM_PERIAPSIS_REMAINING,
  CIRCULARIZATION_SOFT_TRIM_THROTTLE,
  CIRCULARIZATION_TARGET_APOAPSIS,
  CIRCULARIZATION_TARGET_PERIAPSIS,
  CIRCULARIZATION_TIME_TO_APOAPSIS_BAND,
  CIRCULARIZATION_TIME_TO_APOAPSIS_MAX_THROTTLE,
  CIRCULARIZATION_TIME_TO_APOAPSIS_MIN_THROTTLE,
  CIRCULARIZATION_TIME_TO_APOAPSIS_SLOPE,
  CIRCULARIZATION_TIME_TO_APOAPSIS_TARGET,
  CIRCULARIZATION_TOURISM_PERIAPSIS,
  LAUNCH_ASCENT_FAILURE_ALTITUDE,
  LAUNCH_ASCENT_FAILURE_VERTICAL_SPEED,
  RAILS_WARP_FACTOR,
)
from .control import (
  coast_to_ut,
  maintain_coast_warp,
  manual_physics_warp_until,
  read_autopilot_error,
  wait_for_autopilot_alignment,
)
from .descent import configure_suborbital_landing
from .vessel import parachutes_have_deployed, stage_has_engine

def is_falling_before_space():
  return (
    TLM.read("altitude") < LAUNCH_ASCENT_FAILURE_ALTITUDE and
    TLM.read("vertical_speed") <= LAUNCH_ASCENT_FAILURE_VERTICAL_SPEED
  )

def ascent_failed(vessel):
  return is_falling_before_space() or parachutes_have_deployed(vessel)

def circularization_failed(vessel, reached_space):
  if parachutes_have_deployed(vessel):
    return True

  return not reached_space and is_falling_before_space()

def update_reached_space(reached_space):
  return reached_space or TLM.read("altitude") >= CIRCULARIZATION_ATMOSPHERE_ALTITUDE


def record_falling_before_space(event):
  record_mission_event(
    event,
    "Launch",
    altitude=TLM.read("altitude"),
    vertical_speed=TLM.read("vertical_speed"),
    apoapsis=TLM.read("apoapsis"),
    periapsis=TLM.read("periapsis"),
    time_to_apoapsis=TLM.read("time_to_apoapsis"),
  )

def record_parachute_ascent_failure():
  record_mission_event(
    "circularization_parachute_deployed",
    "Launch",
    altitude=TLM.read("altitude"),
    vertical_speed=TLM.read("vertical_speed"),
    apoapsis=TLM.read("apoapsis"),
    periapsis=TLM.read("periapsis"),
    time_to_apoapsis=TLM.read("time_to_apoapsis"),
  )

def record_ascent_failure(event, vessel):
  if parachutes_have_deployed(vessel):
    record_parachute_ascent_failure()
    return

  record_falling_before_space(event)

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

def circularize(conn, vessel, guard, recover_suborbital_failure=True):
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
    abort_condition=lambda: ascent_failed(vessel),
    guard=guard,
  )

  if ascent_failed(vessel):
    record_ascent_failure("circularization_descending_before_atmosphere", vessel)
    return False

  reached_space = update_reached_space(False)

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

  if not wait_for_autopilot_alignment(
    vessel,
    guard,
    "Aiming prograde",
    max_wait=45,
    conn=conn,
    warp_while_waiting=True,
    physics_warp_factor=ASCENT_PHYSICS_WARP_FACTOR,
  ):
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

  try:
    while TLM.read("ut") < circularization_start_ut:
      guard.check()
      TLM.update("Waiting to Circularize")
      reached_space = update_reached_space(reached_space)

      if circularization_failed(vessel, reached_space):
        vessel.control.throttle = 0
        record_ascent_failure("circularization_wait_descending_before_atmosphere", vessel)
        return False

      maintain_coast_warp(
        conn,
        physics_warp_factor=ASCENT_PHYSICS_WARP_FACTOR,
      )
      time.sleep(CIRCULARIZATION_BURN_INTERVAL)
  finally:
    stop_warp(conn)

  guard.check(force=True)
  soft_trim_recorded = False
  time_to_apoapsis_control_recorded = False

  while TLM.read("periapsis") < CIRCULARIZATION_TARGET_PERIAPSIS:
    guard.check()
    TLM.update("Circularizing")
    reached_space = update_reached_space(reached_space)

    if circularization_failed(vessel, reached_space):
      vessel.control.throttle = 0
      record_ascent_failure("circularization_burn_descending_before_atmosphere", vessel)
      return False

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

      if not wait_for_autopilot_alignment(
        vessel,
        guard,
        "Reacquiring prograde",
        max_wait=10,
        conn=conn,
        warp_while_waiting=True,
        physics_warp_factor=ASCENT_PHYSICS_WARP_FACTOR,
      ):
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
        record_mission_event(
          "circularization_suborbital_failure",
          "Launch",
          apoapsis=TLM.read("apoapsis"),
          periapsis=TLM.read("periapsis"),
          recover_suborbital_failure=recover_suborbital_failure,
        )

        if recover_suborbital_failure:
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

