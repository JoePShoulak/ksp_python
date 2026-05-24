# telemetry.py

import math
import threading

G0 = 9.80665

def calc_total_dv(vessel):
  parts = list(vessel.parts.all)
  engines = list(vessel.parts.engines)

  highest_stage = max(
    max(part.stage for part in parts),
    max(part.decouple_stage for part in parts),
  )

  remaining_parts = set(parts)
  total_delta_v = 0

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

      total_thrust = sum(
        engine.available_thrust
        for engine in stage_engines
      )

      if total_thrust <= 0 or dry_mass <= 0 or wet_mass <= dry_mass:
        continue

      total_mass_flow_factor = sum(
        engine.available_thrust / engine.specific_impulse
        for engine in stage_engines
        if engine.specific_impulse > 0
      )

      if total_mass_flow_factor <= 0:
        continue

      combined_isp = total_thrust / total_mass_flow_factor
      stage_delta_v = combined_isp * G0 * math.log(wet_mass / dry_mass)

      total_delta_v += stage_delta_v

    dropped_parts = {
      part
      for part in remaining_parts
      if part.decouple_stage == stage
    }

    remaining_parts -= dropped_parts

  return total_delta_v


class Telemetry:
  def __init__(self):
    self._lock = threading.Lock()
    self._data = {}
    self._getters = {}
    self._warning = "None"
    self._initialized = False

  def begin(self, conn, vessel):
    flight = vessel.flight(vessel.orbit.body.reference_frame)

    altitude = conn.add_stream(getattr, flight, "mean_altitude")
    surface_altitude = conn.add_stream(getattr, flight, "surface_altitude")
    vertical_speed = conn.add_stream(getattr, flight, "vertical_speed")
    speed = conn.add_stream(getattr, flight, "speed")
    time_to_apoapsis = conn.add_stream(getattr, vessel.orbit, 'time_to_apoapsis')
    apoapsis = conn.add_stream(getattr, vessel.orbit, "apoapsis_altitude")
    periapsis = conn.add_stream(getattr, vessel.orbit, "periapsis_altitude")
    ut = conn.add_stream(getattr, conn.space_center, "ut")
    time_to_periapsis = conn.add_stream(getattr, vessel.orbit, "time_to_periapsis")
    liquid_fuel = conn.add_stream(vessel.resources.amount, "LiquidFuel")

    total_dv = calc_total_dv(vessel)

    warning = "None"

    if total_dv < 2500:
      warning = f"Critical dV {round(total_dv)}/3400 for LKO"
    elif total_dv < 3000:
      warning = f"Very low dV {round(total_dv)}/3400 for LKO"
    elif total_dv < 3400:
      warning = f"Low dV {round(total_dv)}/3400 for LKO"
    elif total_dv < 3900:
      warning = f"Marginal dV {round(total_dv)}/3400 for LKO"

    self._warning = warning

    self._getters = {
    "apoapsis": apoapsis,
    "periapsis": periapsis,
    "altitude": altitude,
    "surface_altitude": surface_altitude,
    "vertical_speed": vertical_speed,
    "speed": speed,
    "ut": ut,
    "time_to_apoapsis": time_to_apoapsis,
    "time_to_periapsis": time_to_periapsis,
    "liquid_fuel": liquid_fuel,
    "stage": lambda: vessel.control.current_stage,
    "throttle": lambda: vessel.control.throttle,
    "available_thrust": lambda: vessel.available_thrust,
    "situation": lambda: str(vessel.situation),
    "warning": lambda: self._warning,
    }

    self._initialized = True
    self.update("Telemetry initialized")

  def read(self, name):
    if not self._initialized:
      raise RuntimeError("Telemetry has not been initialized. Call TLM.begin(conn, vessel) first.")

    if name not in self._getters:
      raise KeyError(f"No telemetry stream named {name}")

    return self._getters[name]()

  def streams(self, status="nominal"):
    if not self._initialized:
      return {}

    values = {
      "status": status,
    }

    for name, getter in self._getters.items():
      values[name] = getter()

    return values

  def update(self, status="nominal"):
    values = self.streams(status)

    with self._lock:
      self._data.update(values)

  def get_snapshot(self):
    with self._lock:
      return dict(self._data)


TLM = Telemetry()
