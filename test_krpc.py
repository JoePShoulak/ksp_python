import krpc # type: ignore
import time
from krpc_helper import *

def launch_rocket():
  conn = krpc.connect(name='Sub-orbital flight')

  vessel = conn.space_center.active_vessel

  vessel.auto_pilot.target_pitch_and_heading(90, 90)
  vessel.auto_pilot.engage()
  vessel.control.throttle = 1
  time.sleep(1)

  print('Launch!')
  vessel.control.activate_next_stage()

  # Wait until solid fuel is less than 0.1, then ditch solid fuel boosters
  event = low_fuel(conn, 'SolidFuel', 0.1)
  with event.condition: event.wait()
  print('Booster separation')
  vessel.control.activate_next_stage()

  # Wait til above 10km, then begin gravity turn
  event = above_altitude(conn, 10000)
  with event.condition: event.wait()
  print('Gravity turn')
  vessel.auto_pilot.target_pitch_and_heading(60, 90)

  # Wait til apopapsis is over 100k, then ditch the engine and deactivate controls
  event = apoapsis_above(conn, 100000)
  with event.condition: event.wait()
  print('Launch stage separation')
  vessel.control.throttle = 0
  time.sleep(1)
  vessel.control.activate_next_stage()
  vessel.auto_pilot.disengage()
      
  # Wait til under 2km then activate chutes
  event = below_altitude(conn, 2000)
  with event.condition: event.wait()
  vessel.control.activate_next_stage()

  # Print alt til landed
  while vessel.flight(vessel.orbit.body.reference_frame).vertical_speed < -0.1:
    print('Altitude = %.1f meters' % vessel.flight().surface_altitude)
    time.sleep(1)
  print('Landed!')
