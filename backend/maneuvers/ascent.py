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

from .circularization import circularize
from .constants import (
  LAUNCH_MIN_CLIMB_ALTITUDE,
  LAUNCH_TARGET_APOAPSIS,
  LAUNCH_VERTICAL_ASCENT_ALTITUDE,
  LAUNCH_VERTICAL_ASCENT_TIMEOUT,
)
from .control import read_autopilot_error, reset_manual_controls
from .descent import configure_suborbital_landing, warp_through_aerobraking
from .vessel import stage_has_engine, vessel_is_down

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

    if vessel_is_down(vessel) or (TLM.read("altitude") < 100 and TLM.read("vertical_speed") < -1):
      vessel.control.throttle = 0
      record_mission_event(
        "launch_ascent_failed",
        "Launch",
        altitude=TLM.read("altitude"),
        vertical_speed=TLM.read("vertical_speed"),
        apoapsis=TLM.read("apoapsis"),
        periapsis=TLM.read("periapsis"),
        situation=TLM.read("situation"),
      )
      raise MissionAborted("Launch stopped because the vessel fell back before reaching orbit")

    current_stage = vessel.control.current_stage
    next_stage = current_stage - 1

    if vessel.available_thrust < 0.1 and stage_has_engine(vessel, next_stage):
      vessel.control.activate_next_stage()

    time.sleep(0.1)

  vessel.control.throttle = 0

def launch_to_orbit():
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

