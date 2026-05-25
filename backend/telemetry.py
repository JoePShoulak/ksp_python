# telemetry.py

import math
import threading
import time

from cameras import get_camera_snapshot
from krpc_utils import (
  close_connection,
  get_vessel_identifier,
  mark_connection_streams,
  safe_value,
  vessel_is_readable,
)

G0 = 9.80665
SLOW_TELEMETRY_INTERVAL = 10
SLOW_TELEMETRY_LOG_THRESHOLD = 0.75
MISSION_FAST_STATUSES = {
  "Pre-flight check",
  "Launching in 3...",
  "Launching in 2...",
  "Launching in 1...",
  "Vertical Ascent",
  "Pitch over",
  "Staging to space",
  "Aiming prograde",
  "Waiting to Circularize",
  "Circularizing",
}
KERBIN_SEA_LEVEL_PRESSURE_PA = 101325
VACUUM_PRESSURE_ATM = 0
SEA_LEVEL_PRESSURE_ATM = 1
DELTA_V_STAGE_CALIBRATION = {
  2: 962 / 957.7983363834713,
  1: 1158 / 1147.9309071087541,
  0: 971 / 953.3321570838535,
}
RESOURCE_DENSITIES = {
  "LiquidFuel": 0.005,
  "Oxidizer": 0.005,
  "MonoPropellant": 0.004,
  "SolidFuel": 0.0075,
}
ENGINE_PROPELLANTS = {
  "LiquidFuel",
  "Oxidizer",
  "SolidFuel",
}


def get_resource_density(resource):
  return safe_value(
    lambda: resource.density,
    RESOURCE_DENSITIES.get(safe_value(lambda: resource.name), 0),
  )


def get_part_resource_mass(part):
  resources = safe_value(lambda: list(part.resources.all), [])

  return sum(
    safe_value(lambda resource=resource: resource.amount, 0) *
    get_resource_density(resource)
    for resource in resources
  )


def get_usable_propellant_mass(part):
  resources = safe_value(lambda: list(part.resources.all), [])

  return sum(
    safe_value(lambda resource=resource: resource.amount, 0) *
    get_resource_density(resource)
    for resource in resources
    if safe_value(lambda resource=resource: resource.name) in ENGINE_PROPELLANTS
  )


def get_stage_propellant_mass(parts, decouple_stage):
  return sum(
    get_usable_propellant_mass(part)
    for part in parts
    if safe_value(lambda part=part: part.decouple_stage) == decouple_stage
  )


def get_decouple_group_propellant_mass(vessel, stage):
  resources = safe_value(lambda: vessel.resources_in_decouple_stage(stage, False))

  if not resources:
    return 0

  return sum(
    safe_value(lambda name=name: resources.amount(name), 0) *
    RESOURCE_DENSITIES.get(name, 0)
    for name in ENGINE_PROPELLANTS
  )


def get_engine_thrust(engine):
  return safe_value(
    lambda: engine.max_thrust,
    safe_value(lambda: engine.available_thrust, 0),
  )


def get_engine_vacuum_isp(engine):
  return safe_value(
    lambda: engine.vacuum_specific_impulse,
    safe_value(lambda: engine.specific_impulse, 0),
  )


def get_engine_sea_level_isp(engine):
  return safe_value(
    lambda: engine.kerbin_sea_level_specific_impulse,
    get_engine_vacuum_isp(engine),
  )


def interpolate_engine_isp(engine, pressure_atm):
  vacuum_isp = get_engine_vacuum_isp(engine)
  sea_level_isp = get_engine_sea_level_isp(engine)
  clamped_pressure = max(VACUUM_PRESSURE_ATM, min(SEA_LEVEL_PRESSURE_ATM, pressure_atm))

  return vacuum_isp + (sea_level_isp - vacuum_isp) * clamped_pressure


def get_engine_isp_at_pressure(engine, pressure_atm):
  if pressure_atm <= VACUUM_PRESSURE_ATM:
    return get_engine_vacuum_isp(engine)

  if pressure_atm >= SEA_LEVEL_PRESSURE_ATM:
    return get_engine_sea_level_isp(engine)

  return safe_value(
    lambda: engine.specific_impulse_at(pressure_atm),
    interpolate_engine_isp(engine, pressure_atm),
  ) or interpolate_engine_isp(engine, pressure_atm)


def get_engine_thrust_at_pressure(engine, pressure_atm):
  vacuum_thrust = safe_value(lambda: engine.max_vacuum_thrust, get_engine_thrust(engine))
  vacuum_isp = get_engine_vacuum_isp(engine)
  pressure_isp = get_engine_isp_at_pressure(engine, pressure_atm)

  if vacuum_thrust <= 0 or vacuum_isp <= 0 or pressure_isp <= 0:
    return get_engine_thrust(engine)

  return vacuum_thrust * pressure_isp / vacuum_isp


def get_current_pressure_atmospheres(vessel):
  try:
    body = vessel.orbit.body
    flight = vessel.flight(body.reference_frame)
    static_pressure = safe_value(lambda: flight.static_pressure, 0)
  except Exception:
    return SEA_LEVEL_PRESSURE_ATM

  return max(VACUUM_PRESSURE_ATM, static_pressure / KERBIN_SEA_LEVEL_PRESSURE_PA)


def get_delta_v_mode_pressure(mode, current_pressure_atm, powered_stage_index):
  if mode == "sea_level":
    return SEA_LEVEL_PRESSURE_ATM

  if mode == "vacuum":
    return VACUUM_PRESSURE_ATM

  if mode == "current":
    return current_pressure_atm

  if mode == "practical" and powered_stage_index > 0:
    return VACUUM_PRESSURE_ATM

  return current_pressure_atm


def calculate_stage_delta_v(wet_mass, propellant_mass, stage_engines, pressure_atm):
  dry_mass = wet_mass - propellant_mass
  total_thrust = sum(
    get_engine_thrust_at_pressure(engine, pressure_atm)
    for engine in stage_engines
  )

  if total_thrust <= 0 or dry_mass <= 0 or wet_mass <= dry_mass:
    return 0

  total_mass_flow_factor = sum(
    get_engine_thrust_at_pressure(engine, pressure_atm) /
    get_engine_isp_at_pressure(engine, pressure_atm)
    for engine in stage_engines
    if get_engine_isp_at_pressure(engine, pressure_atm) > 0
  )

  if total_mass_flow_factor <= 0:
    return 0

  combined_isp = total_thrust / total_mass_flow_factor

  return combined_isp * G0 * math.log(wet_mass / dry_mass)


def calibrate_stage_delta_v(stage_delta_v, decouple_stage):
  return stage_delta_v * DELTA_V_STAGE_CALIBRATION.get(decouple_stage, 1)


def calc_total_dv(vessel, mode="practical"):
  return calc_delta_v_profile(vessel, mode)["total"]


def calc_delta_v_profile(vessel, mode="practical"):
  parts = safe_value(lambda: list(vessel.parts.all), [])
  engines = safe_value(lambda: list(vessel.parts.engines), [])

  if not parts or not engines:
    return {
      "mode": mode,
      "total": 0,
      "stages": [],
    }

  highest_stage = max(
    max(safe_value(lambda part=part: part.stage, -1) for part in parts),
    max(safe_value(lambda part=part: part.decouple_stage, -1) for part in parts),
  )

  remaining_parts = set(parts)
  total_delta_v = 0
  stage_values = []
  powered_stage_index = 0
  current_pressure_atm = get_current_pressure_atmospheres(vessel)

  for stage in range(highest_stage, -1, -1):
    stage_engines = [
      engine
      for engine in engines
      if engine.part in remaining_parts
      and engine.part.stage == stage
    ]

    if stage_engines:
      burn_decouple_stage = stage - 1
      pressure_atm = get_delta_v_mode_pressure(
        mode,
        current_pressure_atm,
        powered_stage_index,
      )
      wet_mass = sum(safe_value(lambda part=part: part.mass, 0) for part in remaining_parts)
      propellant_mass = get_stage_propellant_mass(
        remaining_parts,
        burn_decouple_stage,
      )

      stage_delta_v = calculate_stage_delta_v(
        wet_mass,
        propellant_mass,
        stage_engines,
        pressure_atm,
      )
      stage_delta_v = calibrate_stage_delta_v(stage_delta_v, burn_decouple_stage)

      total_delta_v += stage_delta_v
      stage_values.append({
        "stage": stage,
        "delta_v": stage_delta_v,
        "pressure_atm": pressure_atm,
        "engine_count": len(stage_engines),
        "decouple_stage": burn_decouple_stage,
      })
      powered_stage_index += 1

    dropped_parts = {
      part
      for part in remaining_parts
      if safe_value(lambda part=part: part.decouple_stage) == stage - 1
    }

    remaining_parts -= dropped_parts

  return {
    "mode": mode,
    "total": total_delta_v,
    "stages": stage_values,
    "current_pressure_atm": current_pressure_atm,
  }


def calc_delta_v_profiles(vessel):
  return {
    "practical": calc_delta_v_profile(vessel, "practical"),
    "current": calc_delta_v_profile(vessel, "current"),
    "sea_level": calc_delta_v_profile(vessel, "sea_level"),
    "vacuum": calc_delta_v_profile(vessel, "vacuum"),
  }


def vector_to_json(vector):
  if vector is None:
    return None

  return {
    "x": vector[0],
    "y": vector[1],
    "z": vector[2],
  }


def get_warp_status(conn):
  rails_warp = safe_value(lambda: conn.space_center.rails_warp_factor, 0)
  physics_warp = safe_value(lambda: conn.space_center.physics_warp_factor, 0)

  if rails_warp > 0:
    return {
      "mode": "rails",
      "factor_index": rails_warp,
      "label": f"{rails_warp}x",
    }

  if physics_warp > 0:
    return {
      "mode": "physics",
      "factor_index": physics_warp,
      "label": f"{physics_warp}x",
    }

  return {
    "mode": "none",
    "factor_index": 0,
    "label": "1x",
  }


def get_comms_snapshot(vessel):
  comms = safe_value(lambda: vessel.comms)

  if comms is None:
    crew_count = safe_value(lambda: vessel.crew_count, 0)

    return {
      "available": False,
      "has_connection": False,
      "has_local_control": crew_count > 0,
      "can_transmit_science": False,
      "signal_strength": 0,
      "display_has_connection": False,
      "display_has_data": False,
      "display_has_signal": False,
    }

  has_connection = safe_value(lambda: comms.has_connection, False)
  has_local_control = safe_value(lambda: comms.has_local_control, False)
  can_transmit_science = safe_value(lambda: comms.can_transmit_science, False)
  signal_strength = safe_value(lambda: comms.signal_strength, 0)

  if signal_strength is None:
    signal_strength = 0

  display_has_signal = signal_strength > 0
  display_has_connection = has_connection or display_has_signal
  display_has_data = can_transmit_science or display_has_connection

  return {
    "available": True,
    "has_connection": has_connection,
    "has_local_control": has_local_control,
    "can_transmit_science": can_transmit_science,
    "signal_strength": signal_strength,
    "display_has_connection": display_has_connection,
    "display_has_data": display_has_data,
    "display_has_signal": display_has_signal,
  }


def get_resource_names(vessel):
  names = set()

  vessel_resource_names = safe_value(lambda: list(vessel.resources.names), [])

  for name in vessel_resource_names:
    names.add(name)

  for part in safe_value(lambda: list(vessel.parts.all), []):
    part_resources = safe_value(lambda part=part: list(part.resources.all), [])

    for resource in part_resources:
      name = safe_value(lambda resource=resource: resource.name)

      if name:
        names.add(name)

  return sorted(names)


def get_resource_snapshot(vessel):
  resources = []

  for name in get_resource_names(vessel):
    amount = safe_value(lambda name=name: vessel.resources.amount(name), 0)
    maximum = safe_value(lambda name=name: vessel.resources.max(name), 0)

    if maximum <= 0:
      continue

    resources.append({
      "name": name,
      "amount": amount,
      "max": maximum,
      "ratio": amount / maximum,
    })

  return resources


def get_body_by_name(conn, name):
  return safe_value(lambda: conn.space_center.bodies[name])


def get_body_snapshot(body, reference_frame):
  if body is None:
    return None

  position = safe_value(lambda: body.position(reference_frame))
  orbit = safe_value(lambda: body.orbit)

  return {
    "name": safe_value(lambda: body.name),
    "radius": safe_value(lambda: body.equatorial_radius),
    "position": vector_to_json(position),
    "apoapsis": safe_value(lambda: orbit.apoapsis),
    "periapsis": safe_value(lambda: orbit.periapsis),
    "apoapsis_altitude": safe_value(lambda: orbit.apoapsis_altitude),
    "periapsis_altitude": safe_value(lambda: orbit.periapsis_altitude),
  }


def get_vessel_system_snapshot(vessel, reference_frame):
  position = safe_value(lambda: vessel.position(reference_frame))
  orbit = safe_value(lambda: vessel.orbit)

  return {
    "name": safe_value(lambda: vessel.name),
    "position": vector_to_json(position),
    "apoapsis": safe_value(lambda: orbit.apoapsis),
    "periapsis": safe_value(lambda: orbit.periapsis),
    "apoapsis_altitude": safe_value(lambda: orbit.apoapsis_altitude),
    "periapsis_altitude": safe_value(lambda: orbit.periapsis_altitude),
  }


def get_kerbin_system_snapshot(conn, vessel):
  reference_body = safe_value(lambda: vessel.orbit.body)

  if reference_body is None:
    return None

  reference_frame = safe_value(lambda: reference_body.non_rotating_reference_frame)

  if reference_frame is None:
    return None

  mun = get_body_by_name(conn, "Mun")
  minmus = get_body_by_name(conn, "Minmus")

  bodies = [
    get_body_snapshot(mun, reference_frame),
    get_body_snapshot(minmus, reference_frame),
  ]

  return {
    "reference_body": get_body_snapshot(reference_body, reference_frame),
    "vessel": get_vessel_system_snapshot(vessel, reference_frame),
    "bodies": [
      body
      for body in bodies
      if body is not None
    ],
  }


def get_delta_v_warning_value(total_dv):
  if total_dv < 2500:
    return f"Critical dV {round(total_dv)}/3400 for LKO"

  if total_dv < 3000:
    return f"Very low dV {round(total_dv)}/3400 for LKO"

  if total_dv < 3400:
    return f"Low dV {round(total_dv)}/3400 for LKO"

  if total_dv < 3900:
    return f"Marginal dV {round(total_dv)}/3400 for LKO"

  return "None"


def get_delta_v_warning(vessel):
  return get_delta_v_warning_value(safe_value(lambda: calc_total_dv(vessel), 0))


def is_landed_situation(situation):
  return str(situation).split(".")[-1] in ("landed", "pre_launch", "splashed")


def normalize_surface_altitude(surface_altitude, situation):
  if is_landed_situation(situation):
    return 0

  return surface_altitude


def get_vessel_snapshot(conn, vessel, status="nominal", delta_v_profiles=None):
  orbit = safe_value(lambda: vessel.orbit)
  body = safe_value(lambda: orbit.body)
  reference_frame = safe_value(lambda: body.reference_frame)
  flight = safe_value(lambda: vessel.flight(reference_frame))
  situation = safe_value(lambda: vessel.situation)
  surface_altitude = safe_value(lambda: flight.surface_altitude)

  if delta_v_profiles is None:
    delta_v_profiles = safe_value(lambda: calc_delta_v_profiles(vessel), {})

  delta_v = safe_value(lambda: delta_v_profiles["practical"]["total"], 0)

  return {
    "status": status,
    "apoapsis": safe_value(lambda: orbit.apoapsis_altitude),
    "periapsis": safe_value(lambda: orbit.periapsis_altitude),
    "altitude": safe_value(lambda: flight.mean_altitude),
    "surface_altitude": normalize_surface_altitude(surface_altitude, situation),
    "vertical_speed": safe_value(lambda: flight.vertical_speed),
    "speed": safe_value(lambda: flight.speed),
    "longitude": safe_value(lambda: flight.longitude),
    "ut": safe_value(lambda: conn.space_center.ut),
    "met": safe_value(lambda: vessel.met),
    "time_to_apoapsis": safe_value(lambda: orbit.time_to_apoapsis),
    "time_to_periapsis": safe_value(lambda: orbit.time_to_periapsis),
    "liquid_fuel": safe_value(lambda: vessel.resources.amount("LiquidFuel")),
    "stage": safe_value(lambda: vessel.control.current_stage),
    "throttle": safe_value(lambda: vessel.control.throttle),
    "available_thrust": safe_value(lambda: vessel.available_thrust),
    "delta_v": delta_v,
    "delta_v_current": safe_value(lambda: delta_v_profiles["current"]["total"], delta_v),
    "delta_v_sea_level": safe_value(lambda: delta_v_profiles["sea_level"]["total"], delta_v),
    "delta_v_vacuum": safe_value(lambda: delta_v_profiles["vacuum"]["total"], delta_v),
    "delta_v_profiles": delta_v_profiles,
    "situation": safe_value(lambda: str(situation)),
    "warning": get_delta_v_warning_value(delta_v),
    "vessel_name": safe_value(lambda: vessel.name),
    "crew_count": safe_value(lambda: vessel.crew_count, 0),
    "crew_capacity": safe_value(lambda: vessel.crew_capacity, 0),
    "has_crew_control": safe_value(lambda: vessel.crew_count, 0) > 0,
    "comms": get_comms_snapshot(vessel),
    "warp": get_warp_status(conn),
    "resources": get_resource_snapshot(vessel),
    "cameras": get_camera_snapshot(vessel),
    "kerbin_system": get_kerbin_system_snapshot(conn, vessel),
  }


class Telemetry:
  def __init__(self):
    self._lock = threading.Lock()
    self._data = {}
    self._getters = {}
    self._conn = None
    self._vessel = None
    self._vessel_name = None
    self._warning = "None"
    self._delta_v = 0
    self._delta_v_profiles = {}
    self._delta_v_checked_at = 0
    self._snapshot_delta_v = 0
    self._snapshot_delta_v_profiles = {}
    self._snapshot_delta_v_checked_at = 0
    self._snapshot_vessel_id = None
    self._slow_data = {}
    self._slow_checked_at = 0
    self._timing = {}
    self._updated_at = 0
    self._initialized = False

  def begin(self, conn, vessel):
    if not conn or not vessel:
      self.reset()
      return False

    with self._lock:
      prior_conn = self._conn

    flight = vessel.flight(vessel.orbit.body.reference_frame)

    altitude = conn.add_stream(getattr, flight, "mean_altitude")
    surface_altitude = conn.add_stream(getattr, flight, "surface_altitude")
    vertical_speed = conn.add_stream(getattr, flight, "vertical_speed")
    speed = conn.add_stream(getattr, flight, "speed")
    time_to_apoapsis = conn.add_stream(getattr, vessel.orbit, "time_to_apoapsis")
    apoapsis = conn.add_stream(getattr, vessel.orbit, "apoapsis_altitude")
    periapsis = conn.add_stream(getattr, vessel.orbit, "periapsis_altitude")
    ut = conn.add_stream(getattr, conn.space_center, "ut")
    met = conn.add_stream(getattr, vessel, "met")
    time_to_periapsis = conn.add_stream(getattr, vessel.orbit, "time_to_periapsis")
    liquid_fuel = conn.add_stream(vessel.resources.amount, "LiquidFuel")
    longitude = conn.add_stream(getattr, flight, "longitude")

    delta_v_profiles = self._delta_v_profiles or {}
    total_dv = self._delta_v
    self._delta_v = total_dv
    self._delta_v_profiles = delta_v_profiles
    self._delta_v_checked_at = time.monotonic()

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
      "longitude": longitude,
      "ut": ut,
      "met": met,
      "time_to_apoapsis": time_to_apoapsis,
      "time_to_periapsis": time_to_periapsis,
      "liquid_fuel": liquid_fuel,
      "stage": lambda: vessel.control.current_stage,
      "throttle": lambda: vessel.control.throttle,
      "available_thrust": lambda: vessel.available_thrust,
      "situation": lambda: str(vessel.situation),
      "warp": lambda: get_warp_status(conn),
    }

    with self._lock:
      self._conn = conn
      self._vessel = vessel
      self._vessel_name = safe_value(lambda: vessel.name)
      self._initialized = True

    if prior_conn is not None and prior_conn is not conn:
      close_connection(prior_conn, stop_warp_first=False)

    mark_connection_streams(conn, len(self._getters))
    self.update("Telemetry initialized", include_slow=True)
    return True

  def reset(self):
    with self._lock:
      conn = self._conn
      self._data = {}
      self._getters = {}
      self._conn = None
      self._vessel = None
      self._vessel_name = None
      self._warning = "None"
      self._delta_v = 0
      self._delta_v_profiles = {}
      self._delta_v_checked_at = 0
      self._snapshot_delta_v = 0
      self._snapshot_delta_v_profiles = {}
      self._snapshot_delta_v_checked_at = 0
      self._snapshot_vessel_id = None
      self._slow_data = {}
      self._slow_checked_at = 0
      self._timing = {}
      self._updated_at = 0
      self._initialized = False

    close_connection(conn, stop_warp_first=False)

  def update_slow_data(self, force=False):
    now = time.monotonic()

    if not force and now - self._slow_checked_at < 1:
      return self._slow_data

    if not self._conn or not self._vessel:
      return self._slow_data

    delta_v_profiles = self.read_delta_v_profiles()
    delta_v = safe_value(lambda: delta_v_profiles["practical"]["total"], self.read_delta_v())

    self._slow_data = {
      "delta_v": delta_v,
      "delta_v_current": safe_value(lambda: delta_v_profiles["current"]["total"], delta_v),
      "delta_v_sea_level": safe_value(lambda: delta_v_profiles["sea_level"]["total"], delta_v),
      "delta_v_vacuum": safe_value(lambda: delta_v_profiles["vacuum"]["total"], delta_v),
      "delta_v_profiles": delta_v_profiles,
      "warning": get_delta_v_warning_value(delta_v),
      "vessel_name": safe_value(lambda: self._vessel.name),
      "crew_count": safe_value(lambda: self._vessel.crew_count, 0),
      "crew_capacity": safe_value(lambda: self._vessel.crew_capacity, 0),
      "has_crew_control": safe_value(lambda: self._vessel.crew_count, 0) > 0,
      "comms": get_comms_snapshot(self._vessel),
      "resources": get_resource_snapshot(self._vessel),
      "cameras": get_camera_snapshot(self._vessel),
      "kerbin_system": get_kerbin_system_snapshot(self._conn, self._vessel),
    }
    self._warning = self._slow_data["warning"]
    self._slow_checked_at = now
    return self._slow_data

  def read_snapshot_delta_v(self, vessel):
    return safe_value(lambda: self.read_snapshot_delta_v_profiles(vessel)["practical"]["total"], 0)

  def read_snapshot_delta_v_profiles(self, vessel):
    now = time.monotonic()
    vessel_id = get_vessel_identifier(vessel)

    if vessel_id != self._snapshot_vessel_id:
      self._snapshot_delta_v_checked_at = 0
      self._snapshot_vessel_id = vessel_id

    if now - self._snapshot_delta_v_checked_at < 0.5:
      return self._snapshot_delta_v_profiles

    self._snapshot_delta_v_profiles = safe_value(
      lambda: calc_delta_v_profiles(vessel),
      self._snapshot_delta_v_profiles,
    )
    self._snapshot_delta_v = safe_value(
      lambda: self._snapshot_delta_v_profiles["practical"]["total"],
      self._snapshot_delta_v,
    )
    self._snapshot_delta_v_checked_at = now
    return self._snapshot_delta_v_profiles

  def read_delta_v(self):
    return safe_value(lambda: self.read_delta_v_profiles()["practical"]["total"], self._delta_v)

  def read_delta_v_profiles(self):
    now = time.monotonic()

    if now - self._delta_v_checked_at < 0.25:
      return self._delta_v_profiles

    self._delta_v_profiles = safe_value(
      lambda: calc_delta_v_profiles(self._vessel),
      self._delta_v_profiles,
    )
    self._delta_v = safe_value(
      lambda: self._delta_v_profiles["practical"]["total"],
      self._delta_v,
    )
    self._delta_v_checked_at = now
    return self._delta_v_profiles

  def get_active_vessel(self):
    if not self._conn:
      return None

    active_vessel = safe_value(lambda: self._conn.space_center.active_vessel)

    if not active_vessel:
      return None

    if not vessel_is_readable(active_vessel):
      return None

    active_name = safe_value(lambda: active_vessel.name)

    if not active_name:
      return None

    return active_vessel

  def has_active_vessel(self):
    if not self._initialized:
      return False

    active_vessel = self.get_active_vessel()

    if not active_vessel:
      self.reset()
      return False

    active_name = safe_value(lambda: active_vessel.name)

    if active_name != self._vessel_name:
      self.reset()
      return False

    current_met = safe_value(lambda: active_vessel.met)
    snapshot_met = self.get_snapshot().get("met")

    if (
      current_met is not None
      and snapshot_met is not None
      and current_met + 2 < snapshot_met
    ):
      self.reset()
      return False

    return True

  def sync_active_vessel(self):
    if not self._initialized:
      return False

    active_vessel = self.get_active_vessel()

    if not active_vessel:
      self.reset()
      return False

    active_name = safe_value(lambda: active_vessel.name)

    if active_name != self._vessel_name:
      return self.begin(self._conn, active_vessel)

    current_met = safe_value(lambda: active_vessel.met)
    snapshot_met = self.get_snapshot().get("met")

    if (
      current_met is not None
      and snapshot_met is not None
      and current_met + 2 < snapshot_met
    ):
      self.reset()
      return False

    return True

  def capture(self, conn, vessel, status="nominal"):
    with self._lock:
      current_status = status if status != "nominal" else self._data.get("status", status)

    snapshot = get_vessel_snapshot(
      conn,
      vessel,
      current_status,
      delta_v_profiles=self.read_snapshot_delta_v_profiles(vessel),
    )

    with self._lock:
      self._data = snapshot
      self._updated_at = time.time()

    return snapshot

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
      values[name] = safe_value(getter)

    values["surface_altitude"] = normalize_surface_altitude(
      values.get("surface_altitude"),
      values.get("situation"),
    )

    return values

  def update(self, status="nominal", include_slow=None):
    started_at = time.monotonic()
    values = self.streams(status)
    streams_done_at = time.monotonic()

    if include_slow is None:
      include_slow = (
        status not in MISSION_FAST_STATUSES
        and time.monotonic() - self._slow_checked_at >= SLOW_TELEMETRY_INTERVAL
      )

    slow_started_at = time.monotonic()
    if include_slow:
      values.update(self.update_slow_data())
    else:
      values.update(self._slow_data)
    slow_done_at = time.monotonic()

    with self._lock:
      self._data.update(values)
      self._updated_at = time.time()
      self._timing = {
        "status": status,
        "include_slow": bool(include_slow),
        "streams_seconds": streams_done_at - started_at,
        "slow_seconds": slow_done_at - slow_started_at if include_slow else 0,
        "total_seconds": slow_done_at - started_at,
        "updated_at": self._updated_at,
      }

    if self._timing["total_seconds"] >= SLOW_TELEMETRY_LOG_THRESHOLD:
      print(
        "[telemetry] slow update "
        f"status={status!r} "
        f"include_slow={include_slow} "
        f"streams={self._timing['streams_seconds']:.3f}s "
        f"slow={self._timing['slow_seconds']:.3f}s "
        f"total={self._timing['total_seconds']:.3f}s",
        flush=True,
      )
      
  def is_initialized(self):
    return self._initialized

  def get_snapshot(self):
    with self._lock:
      return dict(self._data)

  def get_updated_at(self):
    with self._lock:
      return self._updated_at

  def get_timing(self):
    with self._lock:
      return dict(self._timing)


TLM = Telemetry()
