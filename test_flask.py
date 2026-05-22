from flask import Flask, jsonify
from Orbit import earth_orbit
from test_krpc import launch_rocket, land_rocket, test

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
    if act == "launch_rocket": launch_rocket_route()
    return f"Request to perform {act} has been sent"

# Launch Rocket
@app.route('/actions', methods=['GET'])
def show_button():
    return """
<form action="/actions/launch_rocket" method="post">
    <input type="submit" value="Launch Rocket!" />
</form>
<form action="/actions/land_rocket" method="post">
    <input type="submit" value="Land Rocket!" />
</form>
<form action="/actions/test" method="post">
    <input type="submit" value="Test!" />
</form>
"""
@app.route('/actions/launch_rocket', methods=['POST'])
def launch_rocket_route():
    launch_rocket()
    return "The rocket has been launched"
@app.route('/actions/land_rocket', methods=['POST'])
def land_rocket_route():
    land_rocket()
    return "The rocket has landed"
@app.route('/actions/test', methods=['POST'])
def test_route():
    test()
    return "The test has been run"

app.run()
