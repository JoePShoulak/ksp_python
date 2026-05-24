from krpc_utils import safe_connect
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
from .constants import CIRCULARIZATION_TOURISM_PERIAPSIS, RAILS_WARP_FACTOR
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

