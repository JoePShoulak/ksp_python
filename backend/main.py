import threading

from flask import Flask, jsonify  # type: ignore

from krpc_utils import close_connection, safe_connect
from mission_state import (
  MissionAborted,
  abort_active_mission_if_stale,
  get_active_mission_status,
  is_vessel_lost_error,
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


def run_action_thread(callback):
  try:
    callback()
  except MissionAborted:
    pass
  except Exception as error:
    if is_vessel_lost_error(error):
      pass


def run_action(action, callback, message):
  global ACTION_THREAD

  with ACTION_LOCK:
    if ACTION_THREAD and ACTION_THREAD.is_alive():
      return jsonify({
        "ok": False,
        "action": action,
        "error": "A mission action is already running",
      }), 409

    ACTION_THREAD = threading.Thread(
      target=run_action_thread,
      args=(callback,),
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
  return jsonify({
    "ok": True,
    "mission": get_active_mission_status(),
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


@app.route("/api/telemetry", methods=["GET"])
def get_telemetry():
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
    host="127.0.0.1",
    port=5000,
    debug=True,
    threaded=True,
    use_reloader=False,
  )
  
