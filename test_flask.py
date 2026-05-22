from flask import Flask, jsonify
from Orbit import earth_orbit
from test_krpc import launch_rocket

app = Flask('KSP Interface app')

# import waitress
# FOR PROD: waitress.serve(app, host=args.ip, port=args.port, threads=32, max_request_body_size=1024 * 1024)

orbits = {"earth": earth_orbit}

# GET EXAMPLE
@app.route('/orbits/<path:arg>', methods=['GET'])
def get_orbit(arg: str):
    return jsonify(orbits[arg].dict()) # No checks

# POST EXAMPLE
@app.route('/actions/<path:act>', methods=['POST'])
def post_act(act: str):
    print(f"Someone just asked us to do {act}")
    if act == "launch_rocket": launch_rocket()
    return f"Request to perform {act} has been sent"

app.run()
