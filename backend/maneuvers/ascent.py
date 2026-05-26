import time

from krpc_utils import safe_connect, safe_value, stop_warp
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

from .circularization import circularize
from .constants import (
  CIRCULARIZATION_TOURISM_PERIAPSIS,
  LAUNCH_ASCENT_FAILURE_ALTITUDE,
  LAUNCH_ASCENT_FAILURE_VERTICAL_SPEED,
  LAUNCH_GUIDANCE_READY_MAX_ERROR,
  LAUNCH_MIN_CLIMB_ALTITUDE,
  LAUNCH_PITCH_OVER_ANGLE,
  LAUNCH_TARGET_APOAPSIS,
  LAUNCH_VERTICAL_ASCENT_ALTITUDE,
  LAUNCH_VERTICAL_ASCENT_TIMEOUT,
)
from .control import read_autopilot_error, reset_manual_controls
from .descent import configure_suborbital_landing, warp_through_aerobraking
from .vessel import parachutes_have_deployed, stage_has_engine, vessel_is_down

class LaunchAscentFailed(MissionAborted):
  pass

def ascent_is_falling(altitude, vertical_speed):
  return (
    altitude < LAUNCH_ASCENT_FAILURE_ALTITUDE and
    vertical_speed <= LAUNCH_ASCENT_FAILURE_VERTICAL_SPEED
  )

def record_ascent_failure(event, altitude, vertical_speed):
  record_mission_event(
    event,
    "Launch",
    altitude=altitude,
    vertical_speed=vertical_speed,
    apoapsis=TLM.read("apoapsis"),
    periapsis=TLM.read("periapsis"),
    situation=TLM.read("situation"),
  )

def check_ascent_failed(vessel, guard, event):
  guard.check()
  altitude = TLM.read("altitude")
  vertical_speed = TLM.read("vertical_speed")

  if ascent_is_falling(altitude, vertical_speed):
    vessel.control.throttle = 0
    record_ascent_failure(event, altitude, vertical_speed)
    raise LaunchAscentFailed(
      "Launch stopped because the vessel began descending before reaching space"
    )

  if parachutes_have_deployed(vessel):
    vessel.control.throttle = 0
    record_ascent_failure("launch_ascent_parachute_deployed", altitude, vertical_speed)
    raise LaunchAscentFailed(
      "Launch stopped because parachutes deployed during ascent"
    )

def set_launch_guidance(vessel):
  before_error = read_autopilot_error(vessel)
  safe_value(lambda: vessel.auto_pilot.disengage())
  reset_manual_controls(vessel)
  safe_value(lambda: setattr(vessel.control, "sas", False))
  safe_value(lambda: setattr(vessel.control, "rcs", False))
  time.sleep(0.5)
  safe_value(lambda: setattr(vessel.auto_pilot, "reference_frame", vessel.surface_reference_frame))
  vessel.auto_pilot.target_pitch_and_heading(90, 90)
  vessel.auto_pilot.target_roll = 0
  vessel.auto_pilot.engage()
  vessel.auto_pilot.target_pitch_and_heading(90, 90)
  vessel.auto_pilot.target_roll = 0
  record_mission_event(
    "launch_guidance_reset",
    "Launch",
    autopilot_error_before=before_error,
    autopilot_error_after=read_autopilot_error(vessel),
  )

def wait_for_launch_guidance_ready(vessel, guard):
  started_at = time.monotonic()
  last_error = None
  set_launch_guidance(vessel)

  while time.monotonic() - started_at < 5:
    guard.check()
    safe_value(lambda: setattr(vessel.auto_pilot, "reference_frame", vessel.surface_reference_frame))
    vessel.auto_pilot.target_pitch_and_heading(90, 90)
    vessel.auto_pilot.target_roll = 0
    last_error = read_autopilot_error(vessel)

    if last_error is None or abs(last_error) <= LAUNCH_GUIDANCE_READY_MAX_ERROR:
      return True

    time.sleep(0.2)

  record_mission_event(
    "launch_vertical_guidance_not_ready",
    "Launch",
    autopilot_error=last_error,
    maximum_error=LAUNCH_GUIDANCE_READY_MAX_ERROR,
  )
  return False

def launch(conn, vessel, guard):
  guard.check(force=True)
  TLM.update("Pre-flight check")
  stop_warp(conn)
  reset_manual_controls(vessel)
  vessel.control.sas = False
  vessel.control.rcs = False

  wait_for_launch_guidance_ready(vessel, guard)

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
  check_ascent_failed(
    vessel,
    guard,
    "launch_vertical_ascent_descending_before_space",
  )

  ascent_started_at = time.monotonic()
  while TLM.read("altitude") < LAUNCH_VERTICAL_ASCENT_ALTITUDE:
    TLM.update("Vertical Ascent")
    check_ascent_failed(
      vessel,
      guard,
      "launch_vertical_ascent_descending_before_space",
    )
    altitude = TLM.read("altitude")
    vertical_speed = TLM.read("vertical_speed")

    if (
      time.monotonic() - ascent_started_at > LAUNCH_VERTICAL_ASCENT_TIMEOUT or
      (
        time.monotonic() - ascent_started_at > 8 and
        altitude < LAUNCH_MIN_CLIMB_ALTITUDE
      )
    ):
      vessel.control.throttle = 0
      record_mission_event(
        "launch_vertical_ascent_failed",
        "Launch",
        altitude=altitude,
        vertical_speed=vertical_speed,
        apoapsis=TLM.read("apoapsis"),
        periapsis=TLM.read("periapsis"),
      )
      raise LaunchAscentFailed("Launch failed to climb high enough")

    time.sleep(0.1)

def gravity_turn_to_orbit(conn, vessel, guard):
  guard.check(force=True)
  TLM.update("Pitch over")
  vessel.auto_pilot.target_pitch_and_heading(LAUNCH_PITCH_OVER_ANGLE, 90)

  for _ in range(70):
    time.sleep(0.1)
    check_ascent_failed(
      vessel,
      guard,
      "launch_pitch_over_descending_before_space",
    )

  vessel.auto_pilot.reference_frame = vessel.surface_velocity_reference_frame
  vessel.auto_pilot.target_direction = (0, 1, 0)
  vessel.auto_pilot.target_roll = 0

  while TLM.read("apoapsis") < LAUNCH_TARGET_APOAPSIS:
    TLM.update("Staging to space")
    check_ascent_failed(
      vessel,
      guard,
      "launch_ascent_descending_before_atmosphere",
    )
    altitude = TLM.read("altitude")
    vertical_speed = TLM.read("vertical_speed")

    if vessel_is_down(vessel) or (altitude < 100 and vertical_speed < -1):
      vessel.control.throttle = 0
      record_ascent_failure(
        "launch_ascent_failed",
        altitude,
        vertical_speed,
      )
      raise LaunchAscentFailed("Launch stopped because the vessel fell back before reaching orbit")

    current_stage = vessel.control.current_stage
    next_stage = current_stage - 1

    if vessel.available_thrust < 0.1 and stage_has_engine(vessel, next_stage):
      vessel.control.activate_next_stage()

    time.sleep(0.1)

  vessel.control.throttle = 0

def revert_orbit_failure_to_launch(conn, vessel, guard, reason="Orbit failed"):
  can_revert = safe_value(lambda: conn.space_center.can_revert_to_launch(), False)

  if not can_revert:
    record_mission_event("launch_orbit_failed_revert_unavailable", "Launch")
    raise MissionAborted(
      f"Launch stopped because {reason.lower()} and KSP cannot revert to launch"
    )

  record_mission_event(
    "launch_orbit_failed_revert_start",
    "Launch",
    apoapsis=TLM.read("apoapsis"),
    periapsis=TLM.read("periapsis"),
    minimum_periapsis=CIRCULARIZATION_TOURISM_PERIAPSIS,
    reason=reason,
  )
  TLM.update(f"{reason}; reverting")
  stop_warp(conn)
  safe_value(lambda: vessel.auto_pilot.disengage())
  safe_value(lambda: setattr(vessel.control, "throttle", 0))
  conn.space_center.revert_to_launch()
  record_mission_event("launch_orbit_failed_revert_done", "Launch")


def launch_to_orbit(revert_on_orbit_failure=False):
  conn, vessel = safe_connect("Launch")
  if not conn:
    raise MissionAborted("Launch stopped because no active vessel is available")

  register_mission_connection(conn, vessel, "Launch")
  guard = MissionGuard(conn, vessel, "Launch")

  try:
    guard.check(force=True)
    record_mission_event("launch_tlm_begin_start", "Launch")

    if not TLM.begin(conn, vessel):
      raise MissionAborted("Launch stopped because telemetry could not attach to the active vessel")

    record_mission_event("launch_tlm_begin_done", "Launch")

    launch(conn, vessel, guard)
    gravity_turn_to_orbit(conn, vessel, guard)
    if not circularize(
      conn,
      vessel,
      guard,
      recover_suborbital_failure=not revert_on_orbit_failure,
    ):
      if revert_on_orbit_failure:
        revert_orbit_failure_to_launch(conn, vessel, guard)
        return False

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
  except LaunchAscentFailed:
    if revert_on_orbit_failure:
      revert_orbit_failure_to_launch(conn, vessel, guard, reason="Launch failed")
      return False

    raise
  except Exception as error:
    if is_vessel_lost_error(error):
      if revert_on_orbit_failure:
        revert_orbit_failure_to_launch(conn, vessel, guard, reason="Vessel lost")
        return False

      raise MissionAborted(mission_aborted_message("Launch")) from error
    raise
  finally:
    close_mission_connection(conn)

