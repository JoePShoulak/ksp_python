import threading
import time

from krpc_utils import (
  close_connection,
  get_vessel_identifier,
  read_vessel_met,
  vessel_is_readable,
)
from telemetry import TLM

ACTIVE_MISSION_LOCK = threading.Lock()
ACTIVE_MISSION = None
VISUAL_RESET_SEQUENCE = 0
MISSION_WATCHDOG_INTERVAL = 0.5
MET_ROLLBACK_TOLERANCE = 0.25
MISSION_EVENTS = []
MISSION_EVENT_LIMIT = 80


class MissionAborted(RuntimeError):
  pass


def record_mission_event(event, phase=None, **details):
  entry = {
    "time": round(time.time(), 3),
    "event": event,
    "phase": phase,
    "details": details,
  }

  with ACTIVE_MISSION_LOCK:
    MISSION_EVENTS.append(entry)
    del MISSION_EVENTS[:-MISSION_EVENT_LIMIT]

  detail_text = f" {details}" if details else ""
  print(f"[mission] {phase or '-'} {event}{detail_text}", flush=True)


def get_mission_events():
  with ACTIVE_MISSION_LOCK:
    return list(MISSION_EVENTS)


def is_vessel_lost_error(error):
  error_text = str(error)

  return (
    "No such vessel" in error_text
    or "WinError 10038" in error_text
    or "not a socket" in error_text
  )


def mission_aborted_message(phase):
  return f"{phase} stopped because the active vessel is no longer available"


def is_graceful_vessel_lost_message(message):
  return "active vessel is no longer available" in str(message)


def close_mission_connection(conn):
  record_mission_event("close_connection")
  close_connection(conn)
  TLM.reset()
  unregister_mission_connection(conn)


def force_close_mission_connection(conn):
  close_connection(conn, stop_warp_first=False)
  TLM.reset()
  increment_visual_reset_sequence()


def increment_visual_reset_sequence():
  global VISUAL_RESET_SEQUENCE

  with ACTIVE_MISSION_LOCK:
    VISUAL_RESET_SEQUENCE += 1
    return VISUAL_RESET_SEQUENCE


def get_visual_reset_sequence():
  with ACTIVE_MISSION_LOCK:
    return VISUAL_RESET_SEQUENCE


def ensure_vessel_available(vessel, phase):
  if not vessel_is_readable(vessel):
    raise MissionAborted(mission_aborted_message(phase))


def register_mission_connection(conn, vessel, phase):
  global ACTIVE_MISSION

  mission = {
    "conn": conn,
    "vessel": vessel,
    "phase": phase,
    "vessel_id": get_vessel_identifier(vessel),
    "last_met": read_vessel_met(vessel),
    "abort_requested": False,
  }

  with ACTIVE_MISSION_LOCK:
    ACTIVE_MISSION = mission

  record_mission_event(
    "register_connection",
    phase,
    vessel_id=mission["vessel_id"],
    met=mission["last_met"],
  )

  watchdog = threading.Thread(
    target=watch_active_mission,
    args=(conn,),
    daemon=True,
    name=f"ksp-{phase.lower()}-watchdog",
  )
  watchdog.start()


def unregister_mission_connection(conn):
  global ACTIVE_MISSION
  phase = None

  with ACTIVE_MISSION_LOCK:
    if ACTIVE_MISSION and ACTIVE_MISSION["conn"] is conn:
      phase = ACTIVE_MISSION["phase"]
      ACTIVE_MISSION = None

  if phase:
    record_mission_event("unregister_connection", phase)


def get_registered_mission():
  with ACTIVE_MISSION_LOCK:
    return ACTIVE_MISSION


def is_registered_mission(conn):
  with ACTIVE_MISSION_LOCK:
    return bool(ACTIVE_MISSION and ACTIVE_MISSION["conn"] is conn)


def mission_abort_was_requested(conn):
  with ACTIVE_MISSION_LOCK:
    return bool(
      ACTIVE_MISSION
      and ACTIVE_MISSION["conn"] is conn
      and ACTIVE_MISSION["abort_requested"]
    )


def abort_active_mission(reason="Mission stopped"):
  global ACTIVE_MISSION

  with ACTIVE_MISSION_LOCK:
    mission = ACTIVE_MISSION

    if mission:
      mission["abort_requested"] = True
      ACTIVE_MISSION = None

  if not mission:
    return False

  record_mission_event("abort", mission["phase"], reason=reason)
  force_close_mission_connection(mission["conn"])
  return True


def abort_active_mission_if_met_rolled_back(vessel, reason):
  mission = get_registered_mission()

  if not mission:
    return False

  current_met = read_vessel_met(vessel)
  last_met = mission["last_met"]

  if current_met is None:
    return False

  if last_met is not None and current_met + MET_ROLLBACK_TOLERANCE < last_met:
    return abort_active_mission(reason)

  with ACTIVE_MISSION_LOCK:
    if ACTIVE_MISSION and ACTIVE_MISSION["conn"] is mission["conn"]:
      ACTIVE_MISSION["last_met"] = max(
        current_met,
        ACTIVE_MISSION["last_met"] if ACTIVE_MISSION["last_met"] is not None else current_met,
      )

  return False


def abort_active_mission_if_stale(active_vessel):
  mission = get_registered_mission()

  if not mission:
    return False

  if not active_vessel or not vessel_is_readable(active_vessel):
    return abort_active_mission("Active vessel disappeared")

  active_vessel_id = get_vessel_identifier(active_vessel)
  mission_vessel_id = mission["vessel_id"]

  if mission_vessel_id and active_vessel_id and active_vessel_id != mission_vessel_id:
    return abort_active_mission("Active vessel changed")

  return abort_active_mission_if_met_rolled_back(active_vessel, "Active vessel MET rolled back")


def validate_active_mission():
  mission = get_registered_mission()

  if not mission:
    return False

  if mission["abort_requested"]:
    abort_active_mission("Mission abort requested")
    return False

  mission_vessel = mission["vessel"]

  if not vessel_is_readable(mission_vessel):
    abort_active_mission("Mission vessel is no longer readable")
    return False

  try:
    active_vessel = mission["conn"].space_center.active_vessel
  except Exception:
    abort_active_mission("Mission connection can no longer reach an active vessel")
    return False

  if not active_vessel or not vessel_is_readable(active_vessel):
    abort_active_mission("Mission connection has no active vessel")
    return False

  if abort_active_mission_if_met_rolled_back(
    active_vessel,
    "Mission MET rolled back; assuming flight was reverted",
  ):
    return False

  mission_vessel_id = mission["vessel_id"]
  active_vessel_id = get_vessel_identifier(active_vessel)

  if mission_vessel_id and active_vessel_id and mission_vessel_id != active_vessel_id:
    abort_active_mission("Mission active vessel changed")
    return False

  return True


def watch_active_mission(conn):
  while is_registered_mission(conn):
    time.sleep(MISSION_WATCHDOG_INTERVAL)

    if not is_registered_mission(conn):
      return

    validate_active_mission()


def get_active_mission_status():
  mission = get_registered_mission()

  if not mission:
    return {
      "active": False,
      "phase": None,
      "visual_reset_sequence": get_visual_reset_sequence(),
    }

  return {
    "active": True,
    "phase": mission["phase"],
    "visual_reset_sequence": get_visual_reset_sequence(),
  }


class MissionGuard:
  def __init__(self, conn, vessel, phase, check_interval=0.25):
    self.conn = conn
    self.vessel = vessel
    self.phase = phase
    self.check_interval = check_interval
    self.last_check = 0
    self.vessel_id = get_vessel_identifier(vessel)
    self.last_met = read_vessel_met(vessel)

  def check_met(self, vessel):
    current_met = read_vessel_met(vessel)

    if current_met is None:
      return

    if self.last_met is not None and current_met + MET_ROLLBACK_TOLERANCE < self.last_met:
      abort_active_mission("Mission MET rolled back; assuming flight was reverted")
      raise MissionAborted(mission_aborted_message(self.phase))

    self.last_met = max(current_met, self.last_met if self.last_met is not None else current_met)

  def check(self, force=False):
    if mission_abort_was_requested(self.conn):
      raise MissionAborted(mission_aborted_message(self.phase))

    now = time.monotonic()

    if not force and now - self.last_check < self.check_interval:
      return

    self.last_check = now
    ensure_vessel_available(self.vessel, self.phase)

    try:
      active_vessel = self.conn.space_center.active_vessel
    except Exception as error:
      raise MissionAborted(mission_aborted_message(self.phase)) from error

    if not active_vessel or not vessel_is_readable(active_vessel):
      raise MissionAborted(mission_aborted_message(self.phase))

    self.check_met(active_vessel)
    active_vessel_id = get_vessel_identifier(active_vessel)

    if self.vessel_id and active_vessel_id and active_vessel_id != self.vessel_id:
      raise MissionAborted(mission_aborted_message(self.phase))
