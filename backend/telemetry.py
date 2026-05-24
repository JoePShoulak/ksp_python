# telemetry.py

import math
import os
import threading

from config import load_env_file

load_env_file()

G0 = 9.80665

CAMERA_MODULE_PATTERNS = (
  "camera",
  "hullcam",
  "mumechmodulehullcamera",
  "externalcameraselector",
)

CAMERA_EVENT_PATTERNS = (
  "activate",
  "camera",
  "view",
)

CAMERA_STREAM_URL = os.environ.get("KSP_CAMERA_STREAM_URL", "")
CAMERA_STREAM_KIND = os.environ.get("KSP_CAMERA_STREAM_KIND", "image")


def normalize_stream_url(url):
  if not url:
    return None

  if url.startswith(("http://", "https://")):
    return url

  return f"http://{url}"

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


def safe_value(getter, fallback=None):
  try:
    return getter()
  except Exception:
    return fallback


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


def text_matches_any(value, patterns):
  text = str(value or "").lower()

  return any(pattern in text for pattern in patterns)


def get_part_label(part):
  return (
    safe_value(lambda: part.title)
    or safe_value(lambda: part.name)
    or "Camera"
  )


def module_looks_like_camera(module):
  module_name = safe_value(lambda: module.name, "")
  field_names = safe_value(lambda: list(module.fields), [])
  event_names = safe_value(lambda: list(module.events), [])
  action_names = safe_value(lambda: list(module.actions), [])

  candidates = [
    module_name,
    *field_names,
    *event_names,
    *action_names,
  ]

  return any(
    text_matches_any(candidate, CAMERA_MODULE_PATTERNS)
    for candidate in candidates
  )


def get_camera_stream_url(camera):
  if not CAMERA_STREAM_URL:
    return None

  try:
    stream_url = CAMERA_STREAM_URL.format(
      camera_id=camera["id"],
      camera_index=camera["index"],
      part_name=camera["part_name"],
    )
  except Exception:
    stream_url = CAMERA_STREAM_URL

  return normalize_stream_url(stream_url)


def get_camera_snapshot(vessel, selected_camera_id=None):
  cameras = []

  for index, part in enumerate(safe_value(lambda: list(vessel.parts.all), [])):
    modules = safe_value(lambda part=part: list(part.modules), [])
    camera_modules = [
      module
      for module in modules
      if module_looks_like_camera(module)
    ]

    if not camera_modules:
      continue

    part_name = safe_value(lambda part=part: part.name, f"camera-{index}")
    part_label = get_part_label(part)
    module_names = [
      safe_value(lambda module=module: module.name, "")
      for module in camera_modules
    ]

    cameras.append({
      "id": f"{index}:{part_name}",
      "index": len(cameras),
      "part_name": part_name,
      "label": part_label,
      "modules": module_names,
    })

  selected_index = 0

  if selected_camera_id:
    for index, camera in enumerate(cameras):
      if camera["id"] == selected_camera_id:
        selected_index = index
        break

  selected_camera = cameras[selected_index] if cameras else None

  if selected_camera:
    selected_camera = {
      **selected_camera,
      "stream_url": get_camera_stream_url(selected_camera),
      "stream_kind": CAMERA_STREAM_KIND,
    }

  return {
    "available": len(cameras) > 0,
    "count": len(cameras),
    "selected_index": selected_index if cameras else None,
    "selected": selected_camera,
    "cameras": cameras,
  }


def trigger_camera_module(module):
  event_names = safe_value(lambda: list(module.events), [])
  action_names = safe_value(lambda: list(module.actions), [])

  for event_name in event_names:
    if text_matches_any(event_name, CAMERA_EVENT_PATTERNS):
      did_trigger = safe_value(
        lambda event_name=event_name: module.trigger_event(event_name),
        False,
      )

      if did_trigger is not False:
        return True

  for action_name in action_names:
    if text_matches_any(action_name, CAMERA_EVENT_PATTERNS):
      did_trigger = safe_value(
        lambda action_name=action_name: module.set_action(action_name, True),
        False,
      )

      if did_trigger is not False:
        return True

  return False


def is_flight_scene(conn):
  current_scene = safe_value(lambda: conn.space_center.current_game_scene)

  if current_scene is None:
    return False

  scene_name = str(current_scene).lower()

  return scene_name.endswith(".flight") or scene_name == "flight"


def vessel_is_readable(vessel):
  try:
    vessel_name = vessel.name
    orbit = vessel.orbit
    body = orbit.body
    flight = vessel.flight(body.reference_frame)
    _ = flight.mean_altitude
  except Exception:
    return False

  return bool(vessel_name)


def get_delta_v_warning(vessel):
  total_dv = safe_value(lambda: calc_total_dv(vessel), 0)

  if total_dv < 2500:
    return f"Critical dV {round(total_dv)}/3400 for LKO"

  if total_dv < 3000:
    return f"Very low dV {round(total_dv)}/3400 for LKO"

  if total_dv < 3400:
    return f"Low dV {round(total_dv)}/3400 for LKO"

  if total_dv < 3900:
    return f"Marginal dV {round(total_dv)}/3400 for LKO"

  return "None"


def get_vessel_snapshot(conn, vessel, status="nominal", selected_camera_id=None):
  orbit = safe_value(lambda: vessel.orbit)
  body = safe_value(lambda: orbit.body)
  reference_frame = safe_value(lambda: body.reference_frame)
  flight = safe_value(lambda: vessel.flight(reference_frame))

  return {
    "status": status,
    "apoapsis": safe_value(lambda: orbit.apoapsis_altitude),
    "periapsis": safe_value(lambda: orbit.periapsis_altitude),
    "altitude": safe_value(lambda: flight.mean_altitude),
    "surface_altitude": safe_value(lambda: flight.surface_altitude),
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
    "situation": safe_value(lambda: str(vessel.situation)),
    "warning": get_delta_v_warning(vessel),
    "vessel_name": safe_value(lambda: vessel.name),
    "crew_count": safe_value(lambda: vessel.crew_count, 0),
    "crew_capacity": safe_value(lambda: vessel.crew_capacity, 0),
    "has_crew_control": safe_value(lambda: vessel.crew_count, 0) > 0,
    "comms": get_comms_snapshot(vessel),
    "warp": get_warp_status(conn),
    "resources": get_resource_snapshot(vessel),
    "cameras": get_camera_snapshot(vessel, selected_camera_id),
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
    self._selected_camera_id = None
    self._warning = "None"
    self._initialized = False

  def begin(self, conn, vessel):
    if not conn or not vessel:
      self.reset()
      return False

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
      "warning": lambda: self._warning,
      "vessel_name": lambda: vessel.name,
      "crew_count": lambda: safe_value(lambda: vessel.crew_count, 0),
      "crew_capacity": lambda: safe_value(lambda: vessel.crew_capacity, 0),
      "has_crew_control": lambda: safe_value(lambda: vessel.crew_count, 0) > 0,
      "comms": lambda: get_comms_snapshot(vessel),
      "warp": lambda: get_warp_status(conn),
      "resources": lambda: get_resource_snapshot(vessel),
      "cameras": lambda: get_camera_snapshot(
        vessel,
        self._selected_camera_id,
      ),
      "kerbin_system": lambda: get_kerbin_system_snapshot(conn, vessel),
    }

    self._conn = conn
    self._vessel = vessel
    self._vessel_name = safe_value(lambda: vessel.name)
    self._initialized = True
    self.update("Telemetry initialized")
    return True

  def reset(self):
    with self._lock:
      self._data = {}

    self._getters = {}
    self._conn = None
    self._vessel = None
    self._vessel_name = None
    self._selected_camera_id = None
    self._warning = "None"
    self._initialized = False

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

    return True

  def capture(self, conn, vessel, status="nominal"):
    snapshot = get_vessel_snapshot(
      conn,
      vessel,
      status,
      self._selected_camera_id,
    )

    with self._lock:
      self._data = snapshot

    return snapshot

  def cycle_camera(self, vessel=None):
    target_vessel = vessel or self._vessel

    if not target_vessel:
      return get_camera_snapshot(None)

    camera_snapshot = get_camera_snapshot(
      target_vessel,
      self._selected_camera_id,
    )

    if not camera_snapshot["available"]:
      self._selected_camera_id = None
      return camera_snapshot

    next_index = (camera_snapshot["selected_index"] + 1) % camera_snapshot["count"]
    selected_camera = camera_snapshot["cameras"][next_index]
    self._selected_camera_id = selected_camera["id"]

    for part_index, part in enumerate(safe_value(lambda: list(target_vessel.parts.all), [])):
      part_name = safe_value(lambda part=part: part.name, "")
      camera_id = f"{part_index}:{part_name}"

      if camera_id != self._selected_camera_id:
        continue

      for module in safe_value(lambda part=part: list(part.modules), []):
        if module_looks_like_camera(module) and trigger_camera_module(module):
          break

      break

    return get_camera_snapshot(target_vessel, self._selected_camera_id)

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

    return values

  def update(self, status="nominal"):
    values = self.streams(status)

    with self._lock:
      self._data.update(values)
      
  def is_initialized(self):
    return self._initialized

  def get_snapshot(self):
    if not self.has_active_vessel():
      return {}

    with self._lock:
      return dict(self._data)


TLM = Telemetry()
