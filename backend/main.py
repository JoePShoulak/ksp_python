import threading
import traceback

from flask import Flask, jsonify  # type: ignore

from maneuvers.launch import (
  abort_active_mission_if_stale,
  get_active_mission_status,
  land_rocket,
  launch_to_orbit,
  lko_tourism,
  MissionAborted,
  safe_connect,
  wait_one_hour,
)
from telemetry import TLM

app = Flask("KSP Interface app")
KRPC_QUERY_LOCK = threading.Lock()
ACTION_LOCK = threading.Lock()
ACTION_THREAD = None


def is_vessel_lost_error(error):
  return "No such vessel" in str(error)


def action_error_response(action, error):
  print(f"!== Action {action} failed: {error} ==!")
  traceback.print_exc()

def run_action_thread(action, callback):
  try:
    callback()
  except MissionAborted as error:
    print(f"!== Action {action} stopped: {error} ==!")
  except ValueError as error:
    if not is_vessel_lost_error(error):
      action_error_response(action, error)
  except Exception as error:
    if not is_vessel_lost_error(error):
      action_error_response(action, error)


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
      args=(action, callback),
      daemon=True,
      name=f"ksp-{action}",
    )
    ACTION_THREAD.start()

  return jsonify({
    "ok": True,
    "action": action,
    "message": message,
  }), 202

@app.route("/api/status", methods=["GET"])
def status():
  with KRPC_QUERY_LOCK:
    conn, vessel = safe_connect("Status")
    abort_active_mission_if_stale(vessel if conn else None)
    has_vessel = bool(conn and vessel)

    if conn:
      conn.close()

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
    "The rocket launch script has been started",
  )


@app.route("/api/actions/land_rocket", methods=["POST"])
def land_rocket_route():
  return run_action(
    "land_rocket",
    land_rocket,
    "The rocket landing script has been started",
  )


@app.route("/api/actions/wait_one_hour", methods=["POST"])
def wait_one_hour_route():
  return run_action(
    "wait_one_hour",
    wait_one_hour,
    "The wait script has been started",
  )


@app.route("/api/actions/lko_tourism", methods=["POST"])
def lko_tourism_route():
  return run_action(
    "lko_tourism",
    lko_tourism,
    "The LKO tourism script has been started",
  )


@app.route("/api/cameras/cycle", methods=["POST"])
def cycle_camera_route():
  with KRPC_QUERY_LOCK:
    conn, vessel = safe_connect("Camera")
    abort_active_mission_if_stale(vessel if conn else None)

    if not conn or not vessel:
      return jsonify({
        "ok": False,
        "error": "No active vessel available for camera cycling",
      }), 409

    try:
      camera_snapshot = TLM.cycle_camera(vessel)
    finally:
      conn.close()

  return jsonify({
    "ok": True,
    "has_vessel": True,
    "cameras": camera_snapshot,
  })


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
      conn.close()

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
  
