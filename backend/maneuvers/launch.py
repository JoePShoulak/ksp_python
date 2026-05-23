import krpc # type: ignore
import math
import time
import sys

# TODO: Clean all this up, move things into functions, etc
# It's also not working that well

def safe_connect(name):
  try:
    conn = krpc.connect(name=name)
  except ConnectionRefusedError:
    print("!== Error making connection. Is there a reachable kRPC running in KSP? ==!")
    return False, False
  
  vessel = conn.space_center.active_vessel
  return conn, vessel

def launch_rocket():
  turn_start_altitude = 250
  turn_end_altitude = 45000
  target_altitude = 150000

  conn, vessel = safe_connect("Launch")
  if not conn: return

  # Set up streams for telemetry
  ut = conn.add_stream(getattr, conn.space_center, 'ut') # Seems to be "Universal Time" see add_node in use
  altitude = conn.add_stream(getattr, vessel.flight(), 'mean_altitude')
  apoapsis = conn.add_stream(getattr, vessel.orbit, 'apoapsis_altitude')
  stage_2_resources = vessel.resources_in_decouple_stage(stage=2, cumulative=False)
  srb_fuel = conn.add_stream(stage_2_resources.amount, 'SolidFuel')

  # Pre-launch setup
  vessel.control.sas = False
  vessel.control.rcs = False
  vessel.control.throttle = 1.0

  # Countdown...
  print('3...'); time.sleep(1)
  print('2...'); time.sleep(1)
  print('1...'); time.sleep(1)
  print('Launch!')

  # Activate the first stage
  vessel.control.activate_next_stage()
  vessel.auto_pilot.engage()
  vessel.auto_pilot.target_pitch_and_heading(90, 90)

  # Main ascent loop
  srbs_separated = False
  turn_angle = 0
  while True:
    # Gravity turn
    if altitude() > turn_start_altitude and altitude() < turn_end_altitude:
      frac = ((altitude() - turn_start_altitude) /
        (turn_end_altitude - turn_start_altitude))
      new_turn_angle = frac * 90
      if abs(new_turn_angle - turn_angle) > 0.5:
        turn_angle = new_turn_angle
        vessel.auto_pilot.target_pitch_and_heading(90 - turn_angle, 90)

    # Separate SRBs when finished
    if not srbs_separated:
      if srb_fuel() < 0.1:
        vessel.control.activate_next_stage()
        srbs_separated = True
        print('SRBs separated')

    # Decrease throttle when approaching target apoapsis
    if apoapsis() > target_altitude * 0.9:
      print('Approaching target apoapsis')
      break

  # Disable engines when target apoapsis is reached
  vessel.control.throttle = 0.25
  while apoapsis() < target_altitude: pass
  print('Target apoapsis reached')
  vessel.control.throttle = 0.0

  # Wait until out of atmosphere
  print('Coasting out of atmosphere')
  while altitude() < 70500: pass

  # Plan circularization burn (using vis-viva equation)
  print('Planning circularization burn')
  mu = vessel.orbit.body.gravitational_parameter
  r = vessel.orbit.apoapsis
  a1 = vessel.orbit.semi_major_axis
  a2 = r
  v1 = math.sqrt(mu * ((2. / r) - (1. / a1)))
  v2 = math.sqrt(mu * ((2. / r) - (1. / a2)))
  delta_v = v2 - v1
  node = vessel.control.add_node(ut() + vessel.orbit.time_to_apoapsis, prograde=delta_v)

  # Calculate burn time (using rocket equation)
  F = vessel.available_thrust
  g0 = 9.80665
  Isp = vessel.specific_impulse * g0
  m0 = vessel.mass
  m1 = m0 / math.exp(delta_v / Isp)
  flow_rate = F / Isp
  burn_time = (m0 - m1) / flow_rate

  # Orientate ship
  print('Orientating ship for circularization burn')
  vessel.auto_pilot.reference_frame = node.reference_frame
  vessel.auto_pilot.target_direction = (0, 1, 0)
  vessel.auto_pilot.wait()

  # Wait until burn
  print('Waiting until circularization burn')
  burn_ut = ut() + vessel.orbit.time_to_apoapsis - (burn_time / 2.)
  lead_time = 5
  conn.space_center.warp_to(burn_ut - lead_time)

  # Execute burn
  print('Ready to execute burn')
  time_to_apoapsis = conn.add_stream(getattr, vessel.orbit, 'time_to_apoapsis')
  while time_to_apoapsis() - (burn_time / 2.) > 0: pass
  print('Executing burn')
  vessel.control.throttle = 1.0
  time.sleep(burn_time - 0.1)
  print('Fine tuning')
  vessel.control.throttle = 0.05
  remaining_burn = conn.add_stream(node.remaining_burn_vector, node.reference_frame)
  while remaining_burn()[1] > 1: pass # TODO: Should be zero for perfect burn
  vessel.control.throttle = 0.0
  node.remove()

  print('Launch complete')
  conn.close()

def land_rocket():
  conn, vessel = safe_connect("Land")
  if not conn: return

  # Streams
  ut = conn.add_stream(getattr, conn.space_center, 'ut') # Seems to be "Universal Time" see add_node in use
  time_to_apoapsis = conn.add_stream(getattr, vessel.orbit, 'time_to_apoapsis')
  periapsis = conn.add_stream(getattr, vessel.orbit, 'periapsis_altitude')
  time_to_periapsis = conn.add_stream(getattr, vessel.orbit, 'time_to_periapsis')
  liq_fuel = conn.add_stream(vessel.resources.amount, 'LiquidFuel')
  altitude = conn.add_stream(getattr, vessel.flight(), 'mean_altitude')

  # Break orbit
  vessel.auto_pilot.engage()
  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
  conn.space_center.warp_to(ut() + time_to_apoapsis())
  vessel.auto_pilot.target_direction = (0, -1, 0)
  vessel.auto_pilot.wait() # TODO: Not waiting right
  vessel.control.throttle = 0.1
  while periapsis() > 55000:
    time.sleep(0.001) # TODO: Doesn't work with pass, but should
  vessel.control.throttle = 0.0

  # Burn remaining fuel to slow down
  while altitude() > 60000: 
    time.sleep(0.001) # TODO: Doesn't work with pass, but should
  # conn.space_center.warp_to(ut() + time_to_periapsis()) # TODO: Figure out how to warp to atmosphere
  vessel.auto_pilot.target_direction = (0, -1, 0)
  vessel.control.throttle = 1.0
  while liq_fuel() > 0.1:
    if vessel.control.throttle < 1.0:
      vessel.control.throttle = 1.0

  # Dump the engines
  vessel.control.activate_next_stage()

  # Activate chutes, and land
  while altitude() > 5000: 
    time.sleep(0.001) # TODO: Doesn't work with pass, but should
  vessel.control.activate_next_stage()
  
  conn.close()

import math

G0 = 9.80665


def estimate_staged_delta_v(vessel):
    parts = list(vessel.parts.all)
    engines = list(vessel.parts.engines)

    highest_stage = max(
        max(part.stage for part in parts),
        max(part.decouple_stage for part in parts),
    )

    remaining_parts = set(parts)
    total_delta_v = 0
    stage_results = []

    for stage in range(highest_stage, -1, -1):
        stage_engines = [
            engine
            for engine in engines
            if engine.part in remaining_parts
            and engine.part.stage == stage
        ]

        if stage_engines:
            wet_mass = sum(part.mass for part in remaining_parts)

            burn_decouple_stages = {
                engine.part.decouple_stage
                for engine in stage_engines
            }

            burn_parts = [
                part
                for part in remaining_parts
                if part.decouple_stage in burn_decouple_stages
            ]

            propellant_mass = sum(
                part.mass - part.dry_mass
                for part in burn_parts
            )

            dry_mass = wet_mass - propellant_mass

            total_thrust = sum(engine.available_thrust for engine in stage_engines)

            average_isp = sum(
                engine.specific_impulse * engine.available_thrust
                for engine in stage_engines
            ) / total_thrust

            stage_delta_v = average_isp * G0 * math.log(wet_mass / dry_mass)

            total_delta_v += stage_delta_v

            stage_results.append({
                "stage": stage,
                "delta_v": stage_delta_v,
                "wet_mass": wet_mass,
                "dry_mass": dry_mass,
                "isp": average_isp,
            })

        dropped_parts = {
            part
            for part in remaining_parts
            if part.decouple_stage == stage
        }

        remaining_parts -= dropped_parts

    return total_delta_v, stage_results

def test():
  conn, vessel = safe_connect("Land")

  total_dv, stages = estimate_staged_delta_v(vessel)

  if total_dv < 3000: # TODO: implement KSP DV Roadmap object
    print("Rocket will not reach orbit. Performing sub-orbital flight.")
    suborbital_flight(conn, vessel)
  else:
    # launch to orbit
    pass

def vessel_is_down(vessel):
  return vessel.situation in (
      vessel.situation.landed,
      vessel.situation.splashed,
  )


import time
from telemetry import telemetry

def stage_has_engine(vessel, stage_number):
    return any(
        engine.part.stage == stage_number
        for engine in vessel.parts.engines
    )

def suborbital_flight(conn, vessel):
    flight = vessel.flight(vessel.orbit.body.reference_frame)

    altitude = conn.add_stream(getattr, flight, "mean_altitude")
    surface_altitude = conn.add_stream(getattr, flight, "surface_altitude")
    vertical_speed = conn.add_stream(getattr, flight, "vertical_speed")
    speed = conn.add_stream(getattr, flight, "speed")

    def update_telemetry(status="nominal"):
        telemetry.update(
            status=status,
            altitude=altitude(),
            surface_altitude=surface_altitude(),
            vertical_speed=vertical_speed(),
            speed=speed(),
            stage=vessel.control.current_stage,
            throttle=vessel.control.throttle,
            available_thrust=vessel.available_thrust,
            situation=str(vessel.situation),
        )

    update_telemetry("pre_launch")

    vessel.control.sas = False
    vessel.control.rcs = False
    vessel.control.throttle = 1.0

    print("3...")
    update_telemetry("countdown_3")
    time.sleep(1)

    print("2...")
    update_telemetry("countdown_2")
    time.sleep(1)

    print("1...")
    update_telemetry("countdown_1")
    time.sleep(1)

    print("Launch!")
    update_telemetry("launch")

    vessel.control.activate_next_stage()
    vessel.auto_pilot.engage()
    vessel.auto_pilot.target_pitch_and_heading(90, 90)

    while altitude() < 1000:
        update_telemetry("ascending_vertical")
        time.sleep(0.1)

    vessel.auto_pilot.target_pitch_and_heading(75, 90)
    update_telemetry("pitching_over")

    while vessel.control.current_stage > 0:
        update_telemetry("staging")
        current_stage = vessel.control.current_stage
        next_stage = current_stage - 1

        # If advancing by a stage would likely give us more thrust...
        if vessel.available_thrust < 0.1 and stage_has_engine(vessel, next_stage):
            vessel.control.activate_next_stage()
        # If we don't have more engines, and we're now descending...
        elif vertical_speed() < -50:
            vessel.control.activate_next_stage()

        time.sleep(0.1)

    while not vessel_is_down(vessel):
        update_telemetry("descending")
        time.sleep(0.1)

    update_telemetry("landed")
    print("Landed!")
