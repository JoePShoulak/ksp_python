import time

from krpc_utils import close_connection, safe_connect, safe_value
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

from .ascent import launch_to_orbit
from .constants import (
  CIRCULARIZATION_TOURISM_PERIAPSIS,
  LKO_TOURISM_MAX_LAUNCH_ATTEMPTS,
  RAILS_WARP_FACTOR,
)
from .control import manual_rails_warp_until
from .descent import land_rocket

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

def vessel_is_ready_for_retry(vessel):
  situation = str(safe_value(lambda: vessel.situation, "")).split(".")[-1].lower()
  met = safe_value(lambda: float(vessel.met))
  body = safe_value(lambda: vessel.orbit.body)
  flight = safe_value(lambda: vessel.flight(body.reference_frame)) if body else None
  vertical_speed = safe_value(lambda: flight.vertical_speed) if flight else None
  surface_altitude = safe_value(lambda: flight.surface_altitude) if flight else None
  throttle = safe_value(lambda: vessel.control.throttle)

  ready = (
    situation in ("pre_launch", "landed") and
    (met is None or met <= 0.5) and
    (vertical_speed is None or abs(vertical_speed) <= 0.5) and
    (surface_altitude is None or surface_altitude <= 10) and
    (throttle is None or throttle <= 0.01)
  )

  return ready, {
    "situation": situation,
    "met": met,
    "vertical_speed": vertical_speed,
    "surface_altitude": surface_altitude,
    "throttle": throttle,
  }

def wait_for_launch_revert():
  stable_ready_checks = 0

  for attempt in range(120):
    record_mission_event(
      "lko_sequence_revert_wait",
      "lko_tourism",
      attempt=attempt + 1,
      stable_ready_checks=stable_ready_checks,
    )
    conn, vessel = safe_connect("LKO Retry", attempts=1)

    if conn and vessel:
      try:
        ready, details = vessel_is_ready_for_retry(vessel)

        if ready:
          stable_ready_checks += 1
          record_mission_event(
            "lko_sequence_revert_ready_check",
            "lko_tourism",
            attempt=attempt + 1,
            stable_ready_checks=stable_ready_checks,
            **details,
          )

          if stable_ready_checks >= 3:
            return
        else:
          stable_ready_checks = 0
          record_mission_event(
            "lko_sequence_revert_not_ready",
            "lko_tourism",
            attempt=attempt + 1,
            **details,
          )
      finally:
        close_connection(conn, stop_warp_first=False)
    else:
      stable_ready_checks = 0
      record_mission_event(
        "lko_sequence_revert_no_vessel",
        "lko_tourism",
        attempt=attempt + 1,
      )

    time.sleep(0.5)

  raise MissionAborted("LKO tourism stopped because the reverted flight did not become ready")


def lko_tourism(revert_on_failure=False, retry_on_revert=False):
  record_mission_event("lko_sequence_start", "lko_tourism")
  attempt = 1

  while True:
    record_mission_event(
      "lko_sequence_launch_attempt",
      "lko_tourism",
      attempt=attempt,
      revert_on_failure=revert_on_failure,
      retry_on_revert=retry_on_revert,
    )

    if launch_to_orbit(revert_on_orbit_failure=revert_on_failure):
      break

    record_mission_event("lko_sequence_orbit_failed", "lko_tourism", attempt=attempt)

    if not revert_on_failure or not retry_on_revert:
      return

    if attempt >= LKO_TOURISM_MAX_LAUNCH_ATTEMPTS:
      record_mission_event(
        "lko_sequence_retry_limit_reached",
        "lko_tourism",
        attempt=attempt,
        maximum_attempts=LKO_TOURISM_MAX_LAUNCH_ATTEMPTS,
      )
      raise MissionAborted(
        "LKO tourism stopped because launch failed repeatedly after revert"
      )

    wait_for_launch_revert()
    attempt += 1

  record_mission_event("lko_sequence_wait_start", "lko_tourism")
  wait_one_hour()
  record_mission_event("lko_sequence_land_start", "lko_tourism")
  land_rocket()
  record_mission_event("lko_sequence_done", "lko_tourism")

