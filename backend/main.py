from flask import Flask, jsonify  # type: ignore

from maneuvers.launch import (
  land_rocket,
  launch_to_orbit,
  lko_tourism,
  safe_connect,
  wait_one_hour,
)
from telemetry import TLM

app = Flask("KSP Interface app")

@app.route("/api/status", methods=["GET"])
def status():
  return jsonify({
    "ok": True,
    "message": "KSP Interface API is running",
    "has_vessel": TLM.is_initialized(),
  })


@app.route("/api/actions/launch_rocket", methods=["POST"])
def launch_rocket_route():
  launch_to_orbit()
  return jsonify({
    "ok": True,
    "action": "launch_rocket",
    "message": "The rocket launch script has been started",
  })


@app.route("/api/actions/land_rocket", methods=["POST"])
def land_rocket_route():
  land_rocket()
  return jsonify({
    "ok": True,
    "action": "land_rocket",
    "message": "The rocket landing script has been started",
  })


@app.route("/api/actions/wait_one_hour", methods=["POST"])
def wait_one_hour_route():
  wait_one_hour()
  return jsonify({
    "ok": True,
    "action": "wait_one_hour",
    "message": "The wait script has been started",
  })


@app.route("/api/actions/lko_tourism", methods=["POST"])
def lko_tourism_route():
  lko_tourism()
  return jsonify({
    "ok": True,
    "action": "lko_tourism",
    "message": "The LKO tourism script has been started",
  })


@app.route("/api/telemetry", methods=["GET"])
def get_telemetry():
  if not TLM.is_initialized():
    conn, vessel = safe_connect("Telemetry")

    if conn:
      TLM.begin(conn, vessel)

  snapshot = TLM.get_snapshot()

  return jsonify({
    "ok": True,
    "has_vessel": TLM.is_initialized(),
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
    use_reloader=False,
  )
  