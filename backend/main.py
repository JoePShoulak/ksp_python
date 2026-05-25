import atexit
import os
import threading
import time

from flask import Flask, jsonify, request  # type: ignore

from krpc_utils import close_connection, safe_connect, safe_value, stop_warp
from mission_state import (
  MissionAborted,
  abort_active_mission,
  abort_active_mission_if_stale,
  get_active_mission_status,
  get_registered_mission,
  get_mission_events,
  is_vessel_lost_error,
  record_mission_event,
)
from maneuvers.launch import (
  land_rocket,
  launch_to_orbit,
  lko_tourism,
  wait_one_hour,
)
from telemetry import TLM

app = Flask("KSP Interface app")
KRPC_QUERY_LOCK = threading.Lock()
ACTION_LOCK = threading.Lock()
ACTION_THREAD = None
ACTIVE_ACTION = None
LAST_ACTION_ERROR = None
VIEWPORT_REPORTS = {}
VIEWPORT_LOCK = threading.Lock()
STARTED_AT = time.time()


def log_backend_lifecycle(message):
  print(f"[backend] {message}", flush=True)


atexit.register(lambda: log_backend_lifecycle("exiting"))


def get_cached_vessel_state():
  snapshot = TLM.get_snapshot()

  return {
    "has_cached_telemetry": bool(snapshot),
    "telemetry_initialized": TLM.is_initialized(),
    "cached_vessel_name": snapshot.get("vessel_name"),
  }


def run_action_thread(action, callback):
  global ACTIVE_ACTION, LAST_ACTION_ERROR

  try:
    record_mission_event("action_thread_start", action)
    callback()
  except MissionAborted as error:
    LAST_ACTION_ERROR = str(error)
    record_mission_event("action_aborted", action, error=LAST_ACTION_ERROR)
    pass
  except Exception as error:
    if not is_vessel_lost_error(error):
      LAST_ACTION_ERROR = str(error)
      record_mission_event("action_error", action, error=LAST_ACTION_ERROR)
  finally:
    record_mission_event("action_thread_finish", action)
    TLM.reset()

    with ACTION_LOCK:
      if ACTIVE_ACTION == action:
        ACTIVE_ACTION = None


def run_action(action, callback, message):
  global ACTION_THREAD, ACTIVE_ACTION, LAST_ACTION_ERROR

  with ACTION_LOCK:
    if ACTION_THREAD and ACTION_THREAD.is_alive():
      return jsonify({
        "ok": False,
        "action": action,
        "error": "A mission action is already running",
      }), 409

    LAST_ACTION_ERROR = None
    ACTIVE_ACTION = action
    record_mission_event("action_start_requested", action)
    ACTION_THREAD = threading.Thread(
      target=run_action_thread,
      args=(action, callback),
      daemon=True,
      name=f"ksp-{action}",
    )
    ACTION_THREAD.start()

  return jsonify({
    "ok": True,
    "action": action,
    "started": True,
    "message": message,
  }), 202


@app.route("/api/viewports", methods=["GET", "POST"])
def viewports():
  if request.method == "POST":
    data = request.get_json(silent=True) or {}
    client_id = str(data.get("client_id") or request.remote_addr or "unknown")

    report = {
      **data,
      "client_id": client_id,
      "remote_addr": request.remote_addr,
      "reported_at": time.time(),
    }

    with VIEWPORT_LOCK:
      VIEWPORT_REPORTS[client_id] = report

    print(
      "[viewport] "
      f"{client_id} "
      f"viewport={data.get('viewport_width')}x{data.get('viewport_height')} "
      f"screen={data.get('screen_width')}x{data.get('screen_height')} "
      f"dpr={data.get('device_pixel_ratio')} "
      f"orientation={data.get('orientation')}",
      flush=True,
    )

    return jsonify({
      "ok": True,
      "viewport": report,
    })

  with VIEWPORT_LOCK:
    reports = sorted(
      VIEWPORT_REPORTS.values(),
      key=lambda report: report.get("reported_at", 0),
      reverse=True,
    )

  return jsonify({
    "ok": True,
    "viewports": reports,
  })

@app.route("/api/status", methods=["GET"])
def status():
  if not KRPC_QUERY_LOCK.acquire(blocking=False):
    cached_state = get_cached_vessel_state()

    return jsonify({
      "ok": True,
      "message": "KSP Interface API is running",
      "has_vessel": cached_state["has_cached_telemetry"],
      "vessel_check": "busy",
      **cached_state,
    })

  try:
    conn, vessel = safe_connect("Status")

    if not get_registered_mission():
      abort_active_mission_if_stale(vessel if conn else None)

    has_vessel = bool(conn and vessel)

    if conn:
      close_connection(conn, stop_warp_first=False)
  finally:
    KRPC_QUERY_LOCK.release()

  return jsonify({
    "ok": True,
    "message": "KSP Interface API is running",
    "has_vessel": has_vessel,
    "vessel_check": "fresh",
    **get_cached_vessel_state(),
  })


@app.route("/api/health", methods=["GET"])
def health():
  mission = get_active_mission_status()

  with ACTION_LOCK:
    action = ACTIVE_ACTION if ACTION_THREAD and ACTION_THREAD.is_alive() else None
    last_error = LAST_ACTION_ERROR

  return jsonify({
    "ok": True,
    "message": "KSP Interface API is running",
    "pid": os.getpid(),
    "started_at": STARTED_AT,
    "server_time": time.time(),
    "uptime_seconds": time.time() - STARTED_AT,
    "mission_active": bool(mission.get("active")),
    "action": action,
    "last_error": last_error,
    "krpc_query_busy": KRPC_QUERY_LOCK.locked(),
    **get_cached_vessel_state(),
  })


@app.route("/api/mission", methods=["GET"])
def mission_status():
  mission = get_active_mission_status()

  with ACTION_LOCK:
    action = ACTIVE_ACTION if ACTION_THREAD and ACTION_THREAD.is_alive() else None
    last_error = LAST_ACTION_ERROR

  mission["action"] = action
  mission["last_error"] = last_error
  mission["events"] = get_mission_events()

  return jsonify({
    "ok": True,
    "mission": mission,
  })


@app.route("/api/actions/launch_rocket", methods=["POST"])
def launch_rocket_route():
  return run_action(
    "launch_rocket",
    launch_to_orbit,
    "Launch started",
  )


@app.route("/api/actions/land_rocket", methods=["POST"])
def land_rocket_route():
  return run_action(
    "land_rocket",
    land_rocket,
    "Landing started",
  )


@app.route("/api/actions/wait_one_hour", methods=["POST"])
def wait_one_hour_route():
  return run_action(
    "wait_one_hour",
    wait_one_hour,
    "Wait started",
  )


@app.route("/api/actions/lko_tourism", methods=["POST"])
def lko_tourism_route():
  return run_action(
    "lko_tourism",
    lko_tourism,
    "LKO tourism sequence started",
  )


@app.route("/api/abort", methods=["POST"])
def abort_route():
  abort_active_mission("Abort requested")

  conn, vessel = safe_connect("Abort")

  if conn and vessel:
    try:
      stop_warp(conn)
      safe_value(lambda: vessel.auto_pilot.disengage())
      safe_value(lambda: setattr(vessel.control, "throttle", 0))
      safe_value(lambda: setattr(vessel.control, "abort", True))
      safe_value(lambda: setattr(vessel.control, "sas", True))
      safe_value(lambda: setattr(vessel.control, "rcs", False))
    finally:
      close_connection(conn)

  return jsonify({
    "ok": True,
    "aborted": True,
  }), 202


@app.route("/api/revert-to-launch", methods=["POST"])
def revert_to_launch_route():
  abort_active_mission("Revert to launch requested")

  conn, vessel = safe_connect("Revert")

  if not conn or not vessel:
    TLM.reset()
    return jsonify({
      "ok": False,
      "error": "No active vessel is available to revert",
    }), 409

  try:
    can_revert = safe_value(lambda: conn.space_center.can_revert_to_launch(), False)

    if not can_revert:
      return jsonify({
        "ok": False,
        "error": "KSP cannot currently revert this flight to launch",
      }), 409

    stop_warp(conn)
    safe_value(lambda: vessel.auto_pilot.disengage())
    safe_value(lambda: setattr(vessel.control, "throttle", 0))
    record_mission_event("revert_to_launch_requested", "Revert")
    conn.space_center.revert_to_launch()
    TLM.reset()

    return jsonify({
      "ok": True,
      "reverted": True,
    }), 202
  finally:
    close_connection(conn)


@app.route("/api/telemetry", methods=["GET"])
def get_telemetry():
  snapshot = TLM.get_snapshot()
  mission = get_registered_mission()

  if snapshot:
    if mission or TLM.has_active_vessel():
      if not mission:
        snapshot["status"] = "Idle"

      return jsonify({
        "ok": True,
        "has_vessel": True,
        "telemetry": snapshot,
      })

    TLM.reset()

  if not KRPC_QUERY_LOCK.acquire(blocking=False):
    cached_state = get_cached_vessel_state()

    return jsonify({
      "ok": True,
      "has_vessel": cached_state["has_cached_telemetry"],
      "telemetry": snapshot if snapshot else None,
      "vessel_check": "busy",
      **cached_state,
    })

  try:
    conn, vessel = safe_connect("Telemetry")

    if not get_registered_mission():
      abort_active_mission_if_stale(vessel if conn else None)

    if not conn or not vessel:
      return jsonify({
        "ok": True,
        "has_vessel": False,
        "telemetry": None,
      })

    try:
      snapshot = TLM.capture(conn, vessel, "Idle")
    finally:
      close_connection(conn, stop_warp_first=False)
  finally:
    KRPC_QUERY_LOCK.release()

  return jsonify({
    "ok": True,
    "has_vessel": True,
    "telemetry": snapshot,
    "vessel_check": "fresh",
  })


# HANDLERS
@app.errorhandler(404)
def not_found(error):
  return jsonify({
    "ok": False,
    "error": "Route not found",
  }), 404


@app.errorhandler(500)
def internal_error(error):
  return jsonify({
    "ok": False,
    "error": "Internal server error",
  }), 500


# MAIN
if __name__ == "__main__":
  log_backend_lifecycle("starting")
  app.run(
    host="0.0.0.0",
    port=5000,
    debug=False,
    threaded=True,
    use_reloader=False,
  )
  
