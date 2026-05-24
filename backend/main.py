from flask import Flask, jsonify  # type: ignore

from maneuvers.launch import land_rocket, wait_one_hour, launch_to_orbit, lko_tourism
from telemetry import TLM

app = Flask("KSP Interface app")

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
        launch_to_orbit()
        return jsonify({
            "ok": True,
            "action": act,
            "message": "The rocket launch script has been started",
        })

    if act == "wait_one_hour":
        wait_one_hour()
        return jsonify({
            "ok": True,
            "action": act,
            "message": "The test has been run",
        })

    if act == "land_rocket":
        land_rocket()
        return jsonify({
            "ok": True,
            "action": act,
            "message": "The rocket has landed",
        })

    if act == "lko_tourism":
        lko_tourism()
        return jsonify({
            "ok": True,
            "action": act,
            "message": "The rocket has landed",
        })

    return jsonify({
        "ok": False,
        "error": f"Unknown action: {act}",
    }), 404


@app.route("/api/telemetry", methods=["GET"])
def get_telemetry():
    return jsonify({
        "ok": True,
        "telemetry": TLM.get_snapshot(),
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
