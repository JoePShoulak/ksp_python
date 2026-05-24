import threading

from flask import Flask, jsonify  # type: ignore

from krpc_utils import close_connection, safe_connect, safe_value, stop_warp
from mission_state import (
  MissionAborted,
  abort_active_mission,
  abort_active_mission_if_stale,
  get_active_mission_status,
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


def run_action_thread(action, callback):
  global ACTIVE_ACTION, LAST_ACTION_ERROR

  try:
    record_mission_event("action_thread_start", action)
    callback()
  except MissionAborted:
    record_mission_event("action_aborted", action)
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

@app.route("/api/status", methods=["GET"])
def status():
  with KRPC_QUERY_LOCK:
    conn, vessel = safe_connect("Status")
    abort_active_mission_if_stale(vessel if conn else None)
    has_vessel = bool(conn and vessel)

    if conn:
      close_connection(conn, stop_warp_first=False)

  return jsonify({
    "ok": True,
    "message": "KSP Interface API is running",
    "has_vessel": has_vessel,
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

  if snapshot:
    return jsonify({
      "ok": True,
      "has_vessel": True,
      "telemetry": snapshot,
    })

  with KRPC_QUERY_LOCK:
    conn, vessel = safe_connect("Telemetry")
    abort_active_mission_if_stale(vessel if conn else None)

    if not conn or not vessel:
      return jsonify({
        "ok": True,
        "has_vessel": False,
        "telemetry": None,
      })

    try:
      snapshot = TLM.capture(conn, vessel)
    finally:
      close_connection(conn, stop_warp_first=False)

  return jsonify({
    "ok": True,
    "has_vessel": True,
    "telemetry": snapshot,
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
  app.run(
    host="0.0.0.0",
    port=5000,
    debug=True,
    threaded=True,
    use_reloader=False,
  )
  
