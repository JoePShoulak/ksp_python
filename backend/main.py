from flask import Flask, jsonify  # type: ignore

from misc.Orbit import earth_orbit
from maneuvers.launch import launch_rocket, land_rocket, test, launch_to_orbit
from misc.kOSProcessor import kOSProcessor
from telemetry import telemetry

app = Flask("KSP Interface app")

kos = kOSProcessor()

orbits = {
    "earth": earth_orbit,
}

# ROUTES
# @app.route("/api/orbits/<path:arg>", methods=["GET"])
# def get_orbit(arg: str):
#     if arg not in orbits:
#         return jsonify({
#             "ok": False,
#             "error": f"Unknown orbit: {arg}",
#         }), 404

#     return jsonify({
#         "ok": True,
#         "orbit": orbits[arg].dict(),
#     })

@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({
        "ok": True,
        "message": "KSP Interface API is running",
    })

@app.route("/api/actions/<path:act>", methods=["POST"])
def post_action(act: str):
    print(f"Someone just asked us to do {act}")

    if act == "launch_rocket":
        # kos.connect()
        # kos.run_script("launch_rocket")
        launch_to_orbit()
        return jsonify({
            "ok": True,
            "action": act,
            "message": "The rocket launch script has been started",
        })

    if act == "land_rocket":
        land_rocket()
        return jsonify({
            "ok": True,
            "action": act,
            "message": "The rocket has landed",
        })

    if act == "test":
        test()
        return jsonify({
            "ok": True,
            "action": act,
            "message": "The test has been run",
        })

    return jsonify({
        "ok": False,
        "error": f"Unknown action: {act}",
    }), 404


@app.route("/api/telemetry", methods=["GET"])
def get_telemetry():
    return jsonify({
        "ok": True,
        "telemetry": telemetry.get_snapshot(),
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
