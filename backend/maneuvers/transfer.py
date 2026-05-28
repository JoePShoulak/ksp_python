import math
import time

from krpc_utils import safe_connect, safe_value, stop_warp
from mission_state import (
  MissionAborted,
  MissionGuard,
  close_mission_connection,
  is_vessel_lost_error,
  mission_aborted_message,
  record_mission_event,
  register_mission_connection,
)
from telemetry import TLM

from .ascent import launch_to_orbit
from .circularization import aim_orbital_prograde, read_alignment_error
from .constants import (
  APOAPSIS_CIRCULARIZE_ALIGNMENT_BUFFER,
  APOAPSIS_CIRCULARIZE_COARSE_THROTTLE,
  APOAPSIS_CIRCULARIZE_FINE_THROTTLE,
  APOAPSIS_CIRCULARIZE_LEAD_TIME,
  APOAPSIS_CIRCULARIZE_MEDIUM_THROTTLE,
  APOAPSIS_CIRCULARIZE_PERIAPSIS_TOLERANCE,
  AUTOPILOT_ALIGNMENT_ERROR,
  CIRCULARIZATION_ATMOSPHERE_ALTITUDE,
  MUN_FLYBY_ALIGNMENT_TIMEOUT,
  MUN_FLYBY_APOAPSIS_CUTOFF_MARGIN,
  MUN_FLYBY_APOAPSIS_CIRCULARIZE_MIN_PERIAPSIS,
  MUN_FLYBY_APOAPSIS_MARGIN,
  MUN_FLYBY_BURN_INTERVAL,
  MUN_FLYBY_COARSE_THROTTLE,
  MUN_FLYBY_FINE_THROTTLE,
  MUN_FLYBY_GEOMETRIC_SOI_MARGIN,
  MUN_FLYBY_INCLINATION_ALIGNMENT_ERROR,
  MUN_FLYBY_INCLINATION_ALIGNMENT_TIMEOUT,
  MUN_FLYBY_INCLINATION_PROBE_SECONDS,
  MUN_FLYBY_INCLINATION_TOLERANCE,
  MUN_FLYBY_INCLINATION_TRIM_MAX_SECONDS,
  MUN_FLYBY_INCLINATION_TRIM_THROTTLE,
  MUN_FLYBY_MAX_WAIT_SECONDS,
  MUN_FLYBY_MEDIUM_THROTTLE,
  MUN_FLYBY_MIN_SAFE_PERIAPSIS,
  MUN_FLYBY_PHASE_TOLERANCE,
  MUN_FLYBY_SOI_PERIAPSIS_PROBE_SECONDS,
  MUN_FLYBY_SOI_PERIAPSIS_TOLERANCE,
  MUN_FLYBY_SOI_PERIAPSIS_TRIM_MAX_SECONDS,
  MUN_FLYBY_SOI_PERIAPSIS_TRIM_THROTTLE,
  MUN_FLYBY_SOI_TARGET_PERIAPSIS,
  MUN_FLYBY_TARGET_PERIAPSIS_TOLERANCE,
  MUN_FLYBY_TARGET_PERIAPSIS,
  PERIAPSIS_CIRCULARIZE_ALIGNMENT_BUFFER,
  PERIAPSIS_CIRCULARIZE_APOAPSIS_TOLERANCE,
  PERIAPSIS_CIRCULARIZE_COARSE_THROTTLE,
  PERIAPSIS_CIRCULARIZE_FINE_THROTTLE,
  PERIAPSIS_CIRCULARIZE_LEAD_TIME,
  PERIAPSIS_CIRCULARIZE_MEDIUM_THROTTLE,
  RAILS_WARP_FACTOR,
)
from .control import (
  coast_to_ut,
  maintain_coast_warp,
  manual_physics_warp_until,
  read_autopilot_error,
)
from .vessel import stage_has_engine


def vector_magnitude(vector):
  return math.sqrt(sum(component * component for component in vector))


def vector_subtract(first, second):
  if first is None or second is None:
    return None

  return tuple(
    first_component - second_component
    for first_component, second_component in zip(first, second)
  )


def vector_add_scaled(vector, scaled_vector, scale):
  if vector is None or scaled_vector is None:
    return None

  return tuple(
    component + scaled_component * scale
    for component, scaled_component in zip(vector, scaled_vector)
  )


def vector_dot(first, second):
  if first is None or second is None:
    return None

  return sum(
    first_component * second_component
    for first_component, second_component in zip(first, second)
  )


def vector_distance(first, second):
  if first is None or second is None:
    return None

  return vector_magnitude(
    first_component - second_component
    for first_component, second_component in zip(first, second)
  )


def vector_angle_radians(first, second):
  first_magnitude = vector_magnitude(first)
  second_magnitude = vector_magnitude(second)

  if first_magnitude <= 0 or second_magnitude <= 0:
    return None

  dot_product = sum(
    first_component * second_component
    for first_component, second_component in zip(first, second)
  )
  cosine = max(-1, min(1, dot_product / (first_magnitude * second_magnitude)))
  return math.acos(cosine)


def normalize_angle_degrees(angle):
  return (angle + 180) % 360 - 180


def signed_phase_angle_degrees(vessel, target_body, reference_frame):
  vessel_position = vessel.position(reference_frame)
  target_position = target_body.position(reference_frame)
  unsigned_angle = vector_angle_radians(vessel_position, target_position)

  if unsigned_angle is None:
    return None

  cross_y = (
    vessel_position[2] * target_position[0] -
    vessel_position[0] * target_position[2]
  )
  sign = 1 if cross_y >= 0 else -1
  return normalize_angle_degrees(math.degrees(unsigned_angle) * sign)


def calculate_mun_transfer_plan(vessel, mun):
  kerbin = vessel.orbit.body
  mu = kerbin.gravitational_parameter
  kerbin_radius = kerbin.equatorial_radius
  parking_radius = kerbin_radius + max(
    TLM.read("altitude"),
    TLM.read("periapsis"),
    CIRCULARIZATION_ATMOSPHERE_ALTITUDE,
  )
  mun_orbit_radius = mun.orbit.semi_major_axis
  transfer_radius = mun_orbit_radius
  transfer_axis = (parking_radius + transfer_radius) / 2
  transfer_time = math.pi * math.sqrt((transfer_axis ** 3) / mu)
  mun_mean_motion = math.sqrt(mu / (mun_orbit_radius ** 3))
  lead_angle = normalize_angle_degrees(
    math.degrees(mun_mean_motion * transfer_time) - 180
  )
  circular_speed = math.sqrt(mu / parking_radius)
  transfer_periapsis_speed = math.sqrt(
    mu * ((2 / parking_radius) - (1 / transfer_axis))
  )

  return {
    "body": kerbin.name,
    "target_body": mun.name,
    "target_periapsis": MUN_FLYBY_TARGET_PERIAPSIS,
    "parking_radius": parking_radius,
    "mun_orbit_radius": mun_orbit_radius,
    "target_apoapsis": mun_orbit_radius - kerbin_radius - MUN_FLYBY_APOAPSIS_MARGIN,
    "cutoff_apoapsis": mun_orbit_radius - kerbin_radius - MUN_FLYBY_APOAPSIS_CUTOFF_MARGIN,
    "max_apoapsis": mun_orbit_radius - kerbin_radius + MUN_FLYBY_APOAPSIS_CUTOFF_MARGIN,
    "transfer_time": transfer_time,
    "lead_angle": lead_angle,
    "estimated_delta_v": max(0, transfer_periapsis_speed - circular_speed),
  }


def get_body(conn, name):
  return safe_value(lambda: conn.space_center.bodies[name])


def get_mun_sphere_of_influence(mun):
  return safe_value(lambda: float(mun.sphere_of_influence), 2400000)


def get_mun_distance(vessel, mun, reference_frame):
  vessel_position = safe_value(lambda: vessel.position(reference_frame))
  mun_position = safe_value(lambda: mun.position(reference_frame))
  return vector_distance(vessel_position, mun_position)


def estimate_mun_geometric_intercept(vessel, mun):
  body = safe_value(lambda: vessel.orbit.body)
  reference_frame = safe_value(lambda: body.non_rotating_reference_frame)
  vessel_position = safe_value(lambda: vessel.position(reference_frame))
  vessel_velocity = safe_value(lambda: vessel.velocity(reference_frame))
  mun_position = safe_value(lambda: mun.position(reference_frame))
  mun_velocity = safe_value(lambda: mun.velocity(reference_frame))
  relative_position = vector_subtract(vessel_position, mun_position)
  relative_velocity = vector_subtract(vessel_velocity, mun_velocity)
  mun_soi = get_mun_sphere_of_influence(mun)
  mun_radius = safe_value(lambda: float(mun.equatorial_radius), 200000)

  if relative_position is None or relative_velocity is None:
    return {
      "geometric_intercept": False,
      "mun_sphere_of_influence": mun_soi,
    }

  relative_distance = vector_magnitude(relative_position)
  relative_speed_squared = vector_dot(relative_velocity, relative_velocity)
  closing_component = -vector_dot(relative_position, relative_velocity)
  closing_speed = (
    None
    if relative_distance <= 0
    else closing_component / relative_distance
  )

  if relative_distance <= mun_soi:
    return {
      "geometric_intercept": True,
      "geometric_collision_course": relative_distance <= mun_radius,
      "estimated_mun_miss_distance": relative_distance,
      "estimated_mun_periapsis": relative_distance - mun_radius,
      "estimated_time_to_mun_closest_approach": 0,
      "mun_distance": relative_distance,
      "mun_closing_speed": closing_speed,
      "mun_sphere_of_influence": mun_soi,
    }

  if relative_speed_squared is None or relative_speed_squared <= 0:
    return {
      "geometric_intercept": False,
      "mun_distance": relative_distance,
      "mun_closing_speed": closing_speed,
      "mun_sphere_of_influence": mun_soi,
    }

  time_to_closest = closing_component / relative_speed_squared
  closest_relative_position = vector_add_scaled(
    relative_position,
    relative_velocity,
    time_to_closest,
  )
  miss_distance = (
    None
    if closest_relative_position is None
    else vector_magnitude(closest_relative_position)
  )
  geometric_intercept = (
    time_to_closest > 0
    and miss_distance is not None
    and miss_distance <= mun_soi * MUN_FLYBY_GEOMETRIC_SOI_MARGIN
    and closing_speed is not None
    and closing_speed > 0
  )

  return {
    "geometric_intercept": geometric_intercept,
    "geometric_collision_course": (
      miss_distance is not None and miss_distance <= mun_radius
    ),
    "estimated_mun_miss_distance": miss_distance,
    "estimated_mun_periapsis": (
      None
      if miss_distance is None
      else miss_distance - mun_radius
    ),
    "estimated_time_to_mun_closest_approach": time_to_closest,
    "mun_distance": relative_distance,
    "mun_closing_speed": closing_speed,
    "mun_sphere_of_influence": mun_soi,
  }


def estimate_mun_orbit_intercept(vessel, mun, plan):
  body_name = safe_value(lambda: vessel.orbit.body.name)
  if body_name != "Kerbin":
    return {"orbit_intercept": body_name == "Mun"}

  reference_frame = safe_value(lambda: vessel.orbit.body.non_rotating_reference_frame)
  vessel_orbit = safe_value(lambda: vessel.orbit)
  mun_orbit = safe_value(lambda: mun.orbit)
  now = TLM.read("ut")
  mun_soi = get_mun_sphere_of_influence(mun)
  mun_radius = safe_value(lambda: float(mun.equatorial_radius), 200000)
  scan_seconds = max(plan["transfer_time"] * 1.35, 6 * 3600)
  coarse_step = 300
  best = None

  def sample(offset):
    ut = now + offset
    vessel_position = safe_value(lambda: vessel_orbit.position_at(ut, reference_frame))
    mun_position = safe_value(lambda: mun_orbit.position_at(ut, reference_frame))
    distance = vector_distance(vessel_position, mun_position)

    if distance is None:
      return None

    return {
      "offset": offset,
      "ut": ut,
      "distance": distance,
    }

  offset = 0
  while offset <= scan_seconds:
    sample_result = sample(offset)
    if sample_result is not None and (
      best is None or sample_result["distance"] < best["distance"]
    ):
      best = sample_result
    offset += coarse_step

  if best is None:
    return {
      "orbit_intercept": False,
      "mun_sphere_of_influence": mun_soi,
    }

  fine_start = max(0, best["offset"] - coarse_step)
  fine_end = min(scan_seconds, best["offset"] + coarse_step)
  offset = fine_start

  while offset <= fine_end:
    sample_result = sample(offset)
    if sample_result is not None and sample_result["distance"] < best["distance"]:
      best = sample_result
    offset += 30

  miss_distance = best["distance"]

  return {
    "orbit_intercept": miss_distance <= mun_soi * MUN_FLYBY_GEOMETRIC_SOI_MARGIN,
    "orbit_collision_course": miss_distance <= mun_radius,
    "estimated_orbit_mun_miss_distance": miss_distance,
    "estimated_orbit_mun_periapsis": miss_distance - mun_radius,
    "estimated_orbit_time_to_mun_closest_approach": best["offset"],
    "estimated_orbit_mun_closest_ut": best["ut"],
    "mun_sphere_of_influence": mun_soi,
  }


def read_orbit_patch(vessel):
  orbit = safe_value(lambda: vessel.orbit)
  next_orbit = safe_value(lambda: orbit.next_orbit)

  return {
    "body": safe_value(lambda: orbit.body.name),
    "next_body": safe_value(lambda: next_orbit.body.name),
    "next_periapsis": safe_value(lambda: float(next_orbit.periapsis_altitude)),
    "next_apoapsis": safe_value(lambda: float(next_orbit.apoapsis_altitude)),
    "time_to_soi_change": safe_value(lambda: float(orbit.time_to_soi_change)),
  }


def read_mun_encounter(vessel):
  patch = read_orbit_patch(vessel)

  if patch["next_body"] != "Mun":
    return patch

  return {
    **patch,
    "mun_periapsis": patch["next_periapsis"],
    "mun_apoapsis": patch["next_apoapsis"],
  }


def ensure_kerbin_orbit(vessel):
  body_name = safe_value(lambda: vessel.orbit.body.name)

  if body_name != "Kerbin":
    raise MissionAborted(
      f"Mun flyby stopped because the vessel is orbiting {body_name or 'unknown'}, not Kerbin"
    )

  if TLM.read("periapsis") < CIRCULARIZATION_ATMOSPHERE_ALTITUDE:
    raise MissionAborted("Mun flyby stopped because the vessel is not in stable Kerbin orbit")


def is_stable_kerbin_orbit(vessel):
  return (
    safe_value(lambda: vessel.orbit.body.name) == "Kerbin"
    and TLM.read("periapsis") >= CIRCULARIZATION_ATMOSPHERE_ALTITUDE
  )


def orbit_needs_apoapsis_circularization():
  return (
    TLM.read("apoapsis") - TLM.read("periapsis")
    > APOAPSIS_CIRCULARIZE_PERIAPSIS_TOLERANCE
  )


def mun_flyby_needs_apoapsis_circularization():
  return (
    orbit_needs_apoapsis_circularization()
    and TLM.read("periapsis") < MUN_FLYBY_APOAPSIS_CIRCULARIZE_MIN_PERIAPSIS
  )


def is_launch_ready(vessel):
  situation = str(safe_value(lambda: vessel.situation, "")).split(".")[-1].lower()
  met = safe_value(lambda: float(vessel.met), 0)
  return situation in ("pre_launch", "landed") and met <= 1


def connect_mun_flyby_session():
  conn, vessel = safe_connect("Mun Flyby")

  if not conn:
    record_mission_event("mun_flyby_no_connection", "Mun Flyby")
    raise MissionAborted("Mun flyby stopped because no active vessel is available")

  register_mission_connection(conn, vessel, "Mun Flyby")
  guard = MissionGuard(conn, vessel, "Mun Flyby")
  TLM.begin(conn, vessel)
  return conn, vessel, guard


def estimate_phase_rate_degrees_per_second(vessel, target_body):
  vessel_period = safe_value(lambda: float(vessel.orbit.period), 0)
  target_period = safe_value(lambda: float(target_body.orbit.period), 0)

  if vessel_period <= 0 or target_period <= 0:
    return None

  return 360 / target_period - 360 / vessel_period


def seconds_to_phase_target(phase_error, phase_rate):
  if phase_rate is None or abs(phase_rate) <= 0:
    return None

  candidates = []

  for offset in (-360, 0, 360):
    candidate = (offset - phase_error) / phase_rate
    if candidate > 0:
      candidates.append(candidate)

  if not candidates:
    return None

  return min(candidates)


def wait_for_mun_phase(conn, vessel, mun, plan, guard):
  reference_frame = vessel.orbit.body.non_rotating_reference_frame
  vessel_period = safe_value(lambda: float(vessel.orbit.period), 0)

  if vessel_period <= 0:
    raise MissionAborted("Mun flyby stopped because the Kerbin orbit period could not be measured")

  started_ut = TLM.read("ut")
  deadline_ut = started_ut + min(vessel_period, MUN_FLYBY_MAX_WAIT_SECONDS)
  best_phase = None
  safe_value(lambda: setattr(vessel.control, "throttle", 0))
  safe_value(lambda: vessel.auto_pilot.disengage())
  safe_value(lambda: setattr(vessel.control, "sas", True))
  set_rcs(vessel, False)
  record_mission_event(
    "mun_flyby_phase_wait_controls_released",
    "Mun Flyby",
    sas=safe_value(lambda: vessel.control.sas),
    rcs=safe_value(lambda: vessel.control.rcs),
  )

  while TLM.read("ut") <= deadline_ut:
    guard.check()
    TLM.update("Waiting for Mun transfer window")
    phase_rate = estimate_phase_rate_degrees_per_second(vessel, mun)
    phase_angle = signed_phase_angle_degrees(vessel, mun, reference_frame)

    if phase_angle is None:
      raise MissionAborted("Mun flyby stopped because phase angle could not be measured")

    phase_error = normalize_angle_degrees(phase_angle - plan["lead_angle"])
    phase_score = abs(phase_error)

    if best_phase is None or phase_score < best_phase["phase_score"]:
      best_phase = {
        "phase_angle": phase_angle,
        "phase_error": phase_error,
        "phase_score": phase_score,
        "ut": TLM.read("ut"),
      }

    if abs(phase_error) <= MUN_FLYBY_PHASE_TOLERANCE:
      stop_warp(conn)
      record_mission_event(
        "mun_flyby_phase_ready",
        "Mun Flyby",
        phase_angle=phase_angle,
        phase_error=phase_error,
        target_phase_angle=plan["lead_angle"],
        wait_seconds=TLM.read("ut") - started_ut,
        max_wait_seconds=deadline_ut - started_ut,
      )
      return

    remaining_wait = deadline_ut - TLM.read("ut")
    record_mission_event(
      "mun_flyby_phase_wait",
      "Mun Flyby",
      phase_angle=phase_angle,
      phase_error=phase_error,
      target_phase_angle=plan["lead_angle"],
      phase_rate=phase_rate,
      remaining_wait=remaining_wait,
      best_phase_error=(best_phase or {}).get("phase_error"),
    )
    seconds_until_target = seconds_to_phase_target(phase_error, phase_rate)

    if seconds_until_target is None or seconds_until_target > remaining_wait:
      coast_seconds = min(120, max(5, remaining_wait / 6))
    elif seconds_until_target > 300:
      coast_seconds = max(10, seconds_until_target - 120)
    elif seconds_until_target > 90:
      coast_seconds = max(5, seconds_until_target - 30)
    elif seconds_until_target > 20:
      coast_seconds = max(1, seconds_until_target - 6)
    else:
      coast_seconds = min(1, max(0.2, seconds_until_target / 3))

    coast_seconds = min(coast_seconds, max(0, remaining_wait))

    if coast_seconds <= 0:
      break

    target_ut = TLM.read("ut") + coast_seconds
    record_mission_event(
      "mun_flyby_phase_coast",
      "Mun Flyby",
      target_ut=target_ut,
      coast_seconds=coast_seconds,
      physics_warp=True,
    )
    manual_physics_warp_until(
      conn,
      "Waiting for Mun transfer window",
      lambda: TLM.read("ut") >= target_ut,
      warp_factor=3,
      guard=guard,
    )

  stop_warp(conn)
  record_mission_event(
    "mun_flyby_phase_missed",
    "Mun Flyby",
    target_phase_angle=plan["lead_angle"],
    tolerance=MUN_FLYBY_PHASE_TOLERANCE,
    wait_seconds=TLM.read("ut") - started_ut,
    max_wait_seconds=deadline_ut - started_ut,
    best_phase=best_phase,
  )
  raise MissionAborted(
    "Mun flyby stopped because the transfer window did not arrive within one Kerbin orbit"
  )


def wait_for_transfer_alignment(conn, vessel, guard, alignment_reader=None, max_error=None):
  if alignment_reader is None:
    alignment_reader = lambda: read_alignment_error(vessel)
  if max_error is None:
    max_error = AUTOPILOT_ALIGNMENT_ERROR

  started_at = time.monotonic()
  stable_since = None

  try:
    while time.monotonic() - started_at < MUN_FLYBY_ALIGNMENT_TIMEOUT:
      now = time.monotonic()
      guard.check()
      stop_warp(conn)
      vessel.control.throttle = 0
      TLM.update("Aiming for Mun transfer")
      error = alignment_reader()

      if error is None:
        return False

      if error <= max_error:
        if stable_since is None:
          stable_since = now

        if now - stable_since >= 0.75:
          return True
      else:
        stable_since = None

      time.sleep(0.1)

    return False
  finally:
    stop_warp(conn)


def set_transfer_throttle(vessel, apoapsis_remaining):
  if apoapsis_remaining > 1500000:
    vessel.control.throttle = MUN_FLYBY_COARSE_THROTTLE
  elif apoapsis_remaining > 350000:
    vessel.control.throttle = MUN_FLYBY_MEDIUM_THROTTLE
  else:
    vessel.control.throttle = MUN_FLYBY_FINE_THROTTLE


def set_mun_periapsis_trim_throttle(vessel, periapsis_error):
  if periapsis_error > 250000:
    vessel.control.throttle = MUN_FLYBY_MEDIUM_THROTTLE
  else:
    vessel.control.throttle = MUN_FLYBY_FINE_THROTTLE


def aim_orbital_retrograde(vessel):
  vessel.auto_pilot.engage()
  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
  vessel.auto_pilot.target_direction = (0, -1, 0)
  vessel.auto_pilot.target_roll = 0


def set_rcs(vessel, enabled):
  safe_value(lambda: setattr(vessel.control, "rcs", enabled))


def aim_orbital_direction(vessel, direction):
  safe_value(lambda: setattr(vessel.control, "sas", False))
  set_rcs(vessel, True)
  safe_value(lambda: setattr(vessel.auto_pilot, "stopping_time", (1, 1, 1)))
  safe_value(lambda: setattr(vessel.auto_pilot, "deceleration_time", (1, 1, 1)))
  safe_value(lambda: setattr(vessel.auto_pilot, "attenuation_angle", (1, 1, 1)))
  vessel.auto_pilot.engage()
  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
  vessel.auto_pilot.target_direction = direction
  vessel.auto_pilot.target_roll = 0


def aim_orbital_normal(vessel, sign=1):
  aim_orbital_direction(vessel, (0, 0, sign))


def read_relative_inclination(vessel, target_body):
  return safe_value(lambda: abs(float(vessel.orbit.relative_inclination(target_body.orbit))))


def read_direction_error_degrees(vessel, target_direction):
  vessel_direction = safe_value(lambda: vessel.direction(vessel.orbital_reference_frame))

  if vessel_direction is None:
    return None

  angle = vector_angle_radians(vessel_direction, target_direction)

  if angle is None:
    return None

  return math.degrees(angle)


def wait_for_inclination_alignment(vessel, target_direction, guard):
  started_at = time.monotonic()

  while time.monotonic() - started_at < MUN_FLYBY_INCLINATION_ALIGNMENT_TIMEOUT:
    guard.check()
    TLM.update("Aiming for Mun inclination trim")
    error = read_direction_error_degrees(vessel, target_direction)

    if error is not None and error <= MUN_FLYBY_INCLINATION_ALIGNMENT_ERROR:
      return True

    time.sleep(0.1)

  return False


def mun_inclination_trim_candidates():
  return (
    ("normal", (0, 0, 1)),
    ("anti_normal", (0, 0, -1)),
  )


def trim_mun_inclination(conn, vessel, mun, guard):
  inclination = read_relative_inclination(vessel, mun)

  if inclination is None:
    record_mission_event("mun_flyby_inclination_unavailable", "Mun Flyby")
    return

  if inclination <= MUN_FLYBY_INCLINATION_TOLERANCE:
    record_mission_event(
      "mun_flyby_inclination_skipped",
      "Mun Flyby",
      relative_inclination=inclination,
      tolerance=MUN_FLYBY_INCLINATION_TOLERANCE,
    )
    return

  record_mission_event(
    "mun_flyby_inclination_start",
    "Mun Flyby",
    relative_inclination=inclination,
    tolerance=MUN_FLYBY_INCLINATION_TOLERANCE,
    rcs_enabled=safe_value(lambda: vessel.control.rcs),
  )
  stop_warp(conn)

  best_inclination = inclination
  best_direction = None

  for label, direction in mun_inclination_trim_candidates():
    guard.check()
    stop_warp(conn)
    aim_orbital_direction(vessel, direction)

    if not wait_for_transfer_alignment(
      conn,
      vessel,
      guard,
      alignment_reader=lambda: read_autopilot_abs_error(vessel),
      max_error=MUN_FLYBY_INCLINATION_ALIGNMENT_ERROR,
    ):
      record_mission_event(
        "mun_flyby_inclination_probe_alignment_failed",
        "Mun Flyby",
        direction=label,
        autopilot_error=read_autopilot_error(vessel),
        rcs_enabled=safe_value(lambda: vessel.control.rcs),
      )
      continue

    vessel.control.throttle = MUN_FLYBY_INCLINATION_TRIM_THROTTLE
    time.sleep(MUN_FLYBY_INCLINATION_PROBE_SECONDS)
    vessel.control.throttle = 0
    time.sleep(0.25)
    current_inclination = read_relative_inclination(vessel, mun)

    record_mission_event(
      "mun_flyby_inclination_probe",
      "Mun Flyby",
      direction=label,
      relative_inclination=current_inclination,
      improvement=(
        None
        if current_inclination is None
        else inclination - current_inclination
      ),
    )

    if current_inclination is not None and current_inclination < best_inclination:
      best_inclination = current_inclination
      best_direction = (label, direction)

  if best_direction is None:
    stop_warp(conn)
    safe_value(lambda: setattr(vessel.control, "rcs", False))
    record_mission_event(
      "mun_flyby_inclination_no_improvement",
      "Mun Flyby",
      relative_inclination=read_relative_inclination(vessel, mun),
    )
    return

  best_label, best_vector = best_direction
  aim_orbital_direction(vessel, best_vector)

  if not wait_for_transfer_alignment(
    conn,
    vessel,
    guard,
    alignment_reader=lambda: read_autopilot_abs_error(vessel),
    max_error=MUN_FLYBY_INCLINATION_ALIGNMENT_ERROR,
  ):
    stop_warp(conn)
    safe_value(lambda: setattr(vessel.control, "rcs", False))
    record_mission_event(
      "mun_flyby_inclination_alignment_unsettled",
      "Mun Flyby",
      relative_inclination=read_relative_inclination(vessel, mun),
    )
    return

  started_at = time.monotonic()
  previous_inclination = read_relative_inclination(vessel, mun)

  if previous_inclination is None:
    previous_inclination = best_inclination

  while time.monotonic() - started_at < MUN_FLYBY_INCLINATION_TRIM_MAX_SECONDS:
    guard.check()
    TLM.update("Trimming Mun inclination")
    current_inclination = read_relative_inclination(vessel, mun)

    if current_inclination is None:
      break

    if current_inclination <= MUN_FLYBY_INCLINATION_TOLERANCE:
      break

    if current_inclination > previous_inclination + 0.001:
      break

    previous_inclination = current_inclination
    vessel.control.throttle = MUN_FLYBY_INCLINATION_TRIM_THROTTLE
    time.sleep(MUN_FLYBY_BURN_INTERVAL)

  vessel.control.throttle = 0
  final_inclination = read_relative_inclination(vessel, mun)
  record_mission_event(
    "mun_flyby_inclination_done",
    "Mun Flyby",
    direction=best_label,
    relative_inclination=final_inclination,
    tolerance=MUN_FLYBY_INCLINATION_TOLERANCE,
  )

  if final_inclination is not None and final_inclination > inclination:
    safe_value(lambda: setattr(vessel.control, "rcs", False))
    record_mission_event(
      "mun_flyby_inclination_worse",
      "Mun Flyby",
      relative_inclination=final_inclination,
      starting_relative_inclination=inclination,
    )
    return

  safe_value(lambda: setattr(vessel.control, "rcs", False))


def set_periapsis_circularization_throttle(vessel, apoapsis_remaining):
  if apoapsis_remaining > 50000:
    vessel.control.throttle = PERIAPSIS_CIRCULARIZE_COARSE_THROTTLE
  elif apoapsis_remaining > 10000:
    vessel.control.throttle = PERIAPSIS_CIRCULARIZE_MEDIUM_THROTTLE
  else:
    vessel.control.throttle = PERIAPSIS_CIRCULARIZE_FINE_THROTTLE


def set_apoapsis_circularization_throttle(vessel, periapsis_remaining):
  if periapsis_remaining > 50000:
    vessel.control.throttle = APOAPSIS_CIRCULARIZE_COARSE_THROTTLE
  elif periapsis_remaining > 10000:
    vessel.control.throttle = APOAPSIS_CIRCULARIZE_MEDIUM_THROTTLE
  else:
    vessel.control.throttle = APOAPSIS_CIRCULARIZE_FINE_THROTTLE


def read_autopilot_abs_error(vessel):
  error = read_autopilot_error(vessel)

  if error is None:
    return None

  return abs(error)

def aim_sas_prograde(conn, vessel):
  safe_value(lambda: vessel.auto_pilot.disengage())
  vessel.control.throttle = 0
  vessel.control.sas = True
  safe_value(lambda: setattr(vessel.control, "sas_mode", conn.space_center.SASMode.prograde))
  vessel.control.rcs = True


def mun_encounter_detected(encounter):
  return (
    encounter is not None
    and (
      encounter.get("next_body") == "Mun"
      or encounter.get("geometric_intercept")
      or encounter.get("orbit_intercept")
    )
  )


def perform_mun_injection_burn(conn, vessel, mun, plan, guard):
  set_rcs(vessel, True)
  record_mission_event(
    "mun_flyby_rcs_enabled",
    "Mun Flyby",
    maneuver="injection",
    rcs=safe_value(lambda: vessel.control.rcs),
  )
  aim_sas_prograde(conn, vessel)
  record_mission_event(
    "mun_flyby_alignment_start",
    "Mun Flyby",
    mode="sas_prograde",
    alignment_error=read_alignment_error(vessel),
    autopilot_error=read_autopilot_error(vessel),
  )

  if not wait_for_transfer_alignment(conn, vessel, guard, max_error=12):
    record_mission_event(
      "mun_flyby_alignment_failed",
      "Mun Flyby",
      mode="sas_prograde",
      alignment_error=read_alignment_error(vessel),
      autopilot_error=read_autopilot_error(vessel),
    )
    aim_orbital_prograde(vessel)
    if not wait_for_transfer_alignment(conn, vessel, guard, max_error=12):
      raise MissionAborted("Mun flyby stopped because prograde alignment did not settle")

  record_mission_event(
    "mun_flyby_alignment_done",
    "Mun Flyby",
    alignment_error=read_alignment_error(vessel),
    autopilot_error=read_autopilot_error(vessel),
  )

  encounter = None
  best_encounter = None

  while True:
    guard.check()
    TLM.update("Burning for Mun flyby")
    encounter = read_mun_encounter(vessel)
    geometric_intercept = estimate_mun_geometric_intercept(vessel, mun)
    encounter = {
      **encounter,
      **geometric_intercept,
    }

    alignment_error = read_alignment_error(vessel)
    if alignment_error is not None and alignment_error > 55:
      vessel.control.throttle = 0
      record_mission_event(
        "mun_flyby_alignment_lost",
        "Mun Flyby",
        alignment_error=alignment_error,
        apoapsis=TLM.read("apoapsis"),
        next_body=encounter.get("next_body"),
        mun_periapsis=encounter.get("mun_periapsis"),
        geometric_intercept=encounter.get("geometric_intercept"),
        estimated_mun_miss_distance=encounter.get("estimated_mun_miss_distance"),
        estimated_mun_periapsis=encounter.get("estimated_mun_periapsis"),
        orbit_intercept=encounter.get("orbit_intercept"),
        estimated_orbit_mun_miss_distance=encounter.get(
          "estimated_orbit_mun_miss_distance"
        ),
      )
      aim_sas_prograde(conn, vessel)
      if not wait_for_transfer_alignment(conn, vessel, guard, max_error=55):
        raise MissionAborted("Mun flyby stopped because prograde alignment was lost")

    mun_periapsis = encounter.get("mun_periapsis")

    if mun_periapsis is not None:
      periapsis_error = mun_periapsis - plan["target_periapsis"]
      encounter_score = abs(periapsis_error)

      if best_encounter is None or encounter_score < best_encounter["score"]:
        best_encounter = {
          **encounter,
          "score": encounter_score,
        }

      record_mission_event(
        "mun_flyby_encounter_trim",
        "Mun Flyby",
        mun_periapsis=mun_periapsis,
        periapsis_error=periapsis_error,
        target_mun_periapsis=plan["target_periapsis"],
        time_to_soi_change=encounter.get("time_to_soi_change"),
      )

      if abs(periapsis_error) <= MUN_FLYBY_TARGET_PERIAPSIS_TOLERANCE:
        break

      if mun_periapsis < plan["target_periapsis"] - MUN_FLYBY_TARGET_PERIAPSIS_TOLERANCE:
        if mun_periapsis < MUN_FLYBY_MIN_SAFE_PERIAPSIS:
          vessel.control.throttle = 0
          raise MissionAborted(
            "Mun flyby stopped because the projected Mun periapsis is too low"
          )
        break

      set_mun_periapsis_trim_throttle(vessel, periapsis_error)
    else:
      if (
        encounter.get("geometric_intercept")
        and TLM.read("apoapsis") >= plan["cutoff_apoapsis"]
      ):
        vessel.control.throttle = 0
        record_mission_event(
          "mun_flyby_geometric_intercept_detected",
          "Mun Flyby",
          apoapsis=TLM.read("apoapsis"),
          target_apoapsis=plan["target_apoapsis"],
          cutoff_apoapsis=plan["cutoff_apoapsis"],
          max_apoapsis=plan["max_apoapsis"],
          estimated_mun_miss_distance=encounter.get("estimated_mun_miss_distance"),
          estimated_mun_periapsis=encounter.get("estimated_mun_periapsis"),
          estimated_time_to_mun_closest_approach=encounter.get(
            "estimated_time_to_mun_closest_approach"
          ),
          geometric_collision_course=encounter.get("geometric_collision_course"),
          mun_distance=encounter.get("mun_distance"),
          mun_closing_speed=encounter.get("mun_closing_speed"),
          mun_sphere_of_influence=encounter.get("mun_sphere_of_influence"),
        )
        break

      if TLM.read("apoapsis") >= plan["cutoff_apoapsis"]:
        orbit_intercept = estimate_mun_orbit_intercept(vessel, mun, plan)
        encounter = {
          **encounter,
          **orbit_intercept,
        }

        if encounter.get("orbit_intercept"):
          vessel.control.throttle = 0
          record_mission_event(
            "mun_flyby_orbit_intercept_detected",
            "Mun Flyby",
            apoapsis=TLM.read("apoapsis"),
            target_apoapsis=plan["target_apoapsis"],
            cutoff_apoapsis=plan["cutoff_apoapsis"],
            max_apoapsis=plan["max_apoapsis"],
            estimated_orbit_mun_miss_distance=encounter.get(
              "estimated_orbit_mun_miss_distance"
            ),
            estimated_orbit_mun_periapsis=encounter.get(
              "estimated_orbit_mun_periapsis"
            ),
            estimated_orbit_time_to_mun_closest_approach=encounter.get(
              "estimated_orbit_time_to_mun_closest_approach"
            ),
            estimated_orbit_mun_closest_ut=encounter.get(
              "estimated_orbit_mun_closest_ut"
            ),
            orbit_collision_course=encounter.get("orbit_collision_course"),
            mun_sphere_of_influence=encounter.get("mun_sphere_of_influence"),
          )
          break

      if TLM.read("apoapsis") >= plan["max_apoapsis"]:
        vessel.control.throttle = 0
        raise MissionAborted(
          "Mun flyby stopped because no Mun encounter appeared during transfer burn"
        )

      apoapsis_remaining = plan["target_apoapsis"] - TLM.read("apoapsis")
      set_transfer_throttle(vessel, apoapsis_remaining)

      if TLM.read("apoapsis") >= plan["cutoff_apoapsis"]:
        vessel.control.throttle = MUN_FLYBY_FINE_THROTTLE

    if vessel.available_thrust < 0.1:
      current_stage = vessel.control.current_stage
      next_stage = current_stage - 1
      if stage_has_engine(vessel, next_stage):
        vessel.control.activate_next_stage()
      else:
        vessel.control.throttle = 0
        raise MissionAborted("Mun flyby stopped because the vessel ran out of thrust")

    time.sleep(MUN_FLYBY_BURN_INTERVAL)

  vessel.control.throttle = 0

  if not mun_encounter_detected(encounter):
    raise MissionAborted(
      "Mun flyby stopped because the transfer burn did not produce a Mun encounter"
    )

  record_mission_event(
    "mun_flyby_injection_done",
    "Mun Flyby",
    apoapsis=TLM.read("apoapsis"),
    periapsis=TLM.read("periapsis"),
    target_apoapsis=plan["target_apoapsis"],
    target_mun_periapsis=plan["target_periapsis"],
    next_body=encounter.get("next_body"),
    mun_periapsis=encounter.get("mun_periapsis"),
    best_mun_periapsis=(best_encounter or {}).get("mun_periapsis"),
    time_to_soi_change=encounter.get("time_to_soi_change"),
    geometric_intercept=encounter.get("geometric_intercept"),
    geometric_collision_course=encounter.get("geometric_collision_course"),
    estimated_mun_miss_distance=encounter.get("estimated_mun_miss_distance"),
    estimated_mun_periapsis=encounter.get("estimated_mun_periapsis"),
    estimated_time_to_mun_closest_approach=encounter.get(
      "estimated_time_to_mun_closest_approach"
    ),
    orbit_intercept=encounter.get("orbit_intercept"),
    orbit_collision_course=encounter.get("orbit_collision_course"),
    estimated_orbit_mun_miss_distance=encounter.get(
      "estimated_orbit_mun_miss_distance"
    ),
    estimated_orbit_mun_periapsis=encounter.get("estimated_orbit_mun_periapsis"),
    estimated_orbit_time_to_mun_closest_approach=encounter.get(
      "estimated_orbit_time_to_mun_closest_approach"
    ),
    estimated_orbit_mun_closest_ut=encounter.get("estimated_orbit_mun_closest_ut"),
    mun_distance=encounter.get("mun_distance"),
    mun_closing_speed=encounter.get("mun_closing_speed"),
    mun_sphere_of_influence=encounter.get("mun_sphere_of_influence"),
  )
  set_rcs(vessel, False)
  record_mission_event(
    "mun_flyby_rcs_disabled",
    "Mun Flyby",
    maneuver="injection",
    rcs=safe_value(lambda: vessel.control.rcs),
  )


def read_current_periapsis(vessel):
  return safe_value(lambda: float(vessel.orbit.periapsis_altitude))


def mun_soi_periapsis_trim_candidates():
  return (
    ("radial_out", (1, 0, 0)),
    ("radial_in", (-1, 0, 0)),
    ("normal", (0, 0, 1)),
    ("anti_normal", (0, 0, -1)),
    ("prograde", (0, 1, 0)),
    ("retrograde", (0, -1, 0)),
  )


def mun_soi_periapsis_score(periapsis):
  if periapsis is None:
    return None

  return abs(periapsis - MUN_FLYBY_SOI_TARGET_PERIAPSIS)


def stage_if_needed(vessel):
  if vessel.available_thrust >= 0.1:
    return True

  current_stage = vessel.control.current_stage
  next_stage = current_stage - 1
  if stage_has_engine(vessel, next_stage):
    vessel.control.activate_next_stage()
    return True

  return False


def refine_mun_soi_periapsis(conn, vessel, guard):
  starting_periapsis = read_current_periapsis(vessel)
  starting_score = mun_soi_periapsis_score(starting_periapsis)

  record_mission_event(
    "mun_flyby_soi_periapsis_refine_start",
    "Mun Flyby",
    target_periapsis=MUN_FLYBY_SOI_TARGET_PERIAPSIS,
    tolerance=MUN_FLYBY_SOI_PERIAPSIS_TOLERANCE,
    periapsis=starting_periapsis,
    apoapsis=TLM.read("apoapsis"),
  )

  if starting_score is None:
    record_mission_event(
      "mun_flyby_soi_periapsis_refine_unavailable",
      "Mun Flyby",
    )
    return

  if starting_score <= MUN_FLYBY_SOI_PERIAPSIS_TOLERANCE:
    record_mission_event(
      "mun_flyby_soi_periapsis_refine_skipped",
      "Mun Flyby",
      periapsis=starting_periapsis,
      target_periapsis=MUN_FLYBY_SOI_TARGET_PERIAPSIS,
    )
    return

  best_probe = None
  set_rcs(vessel, True)

  for label, direction in mun_soi_periapsis_trim_candidates():
    guard.check()
    stop_warp(conn)
    before = read_current_periapsis(vessel)
    before_score = mun_soi_periapsis_score(before)

    if before_score is None:
      continue

    aim_orbital_direction(vessel, direction)

    if not wait_for_transfer_alignment(
      conn,
      vessel,
      guard,
      alignment_reader=lambda direction=direction: read_direction_error_degrees(vessel, direction),
      max_error=MUN_FLYBY_INCLINATION_ALIGNMENT_ERROR,
    ):
      record_mission_event(
        "mun_flyby_soi_periapsis_probe_alignment_failed",
        "Mun Flyby",
        direction=label,
        periapsis=before,
      )
      continue

    if not stage_if_needed(vessel):
      record_mission_event(
        "mun_flyby_soi_periapsis_no_thrust",
        "Mun Flyby",
        periapsis=before,
      )
      return

    vessel.control.throttle = MUN_FLYBY_SOI_PERIAPSIS_TRIM_THROTTLE
    time.sleep(MUN_FLYBY_SOI_PERIAPSIS_PROBE_SECONDS)
    vessel.control.throttle = 0
    time.sleep(0.35)

    after = read_current_periapsis(vessel)
    after_score = mun_soi_periapsis_score(after)
    improvement = None if after_score is None else before_score - after_score

    record_mission_event(
      "mun_flyby_soi_periapsis_probe",
      "Mun Flyby",
      direction=label,
      before_periapsis=before,
      after_periapsis=after,
      target_periapsis=MUN_FLYBY_SOI_TARGET_PERIAPSIS,
      improvement=improvement,
    )

    if improvement is not None and improvement > 0 and (
      best_probe is None or improvement > best_probe["improvement"]
    ):
      best_probe = {
        "direction": direction,
        "label": label,
        "improvement": improvement,
        "periapsis": after,
        "score": after_score,
      }

    if after_score is not None and after_score <= MUN_FLYBY_SOI_PERIAPSIS_TOLERANCE:
      record_mission_event(
        "mun_flyby_soi_periapsis_refine_done",
        "Mun Flyby",
        direction=label,
        periapsis=after,
        target_periapsis=MUN_FLYBY_SOI_TARGET_PERIAPSIS,
      )
      set_rcs(vessel, False)
      return

  if best_probe is None:
    record_mission_event(
      "mun_flyby_soi_periapsis_no_probe_improved",
      "Mun Flyby",
      periapsis=read_current_periapsis(vessel),
      target_periapsis=MUN_FLYBY_SOI_TARGET_PERIAPSIS,
    )
    set_rcs(vessel, False)
    return

  aim_orbital_direction(vessel, best_probe["direction"])
  if not wait_for_transfer_alignment(
    conn,
    vessel,
    guard,
    alignment_reader=lambda: read_direction_error_degrees(vessel, best_probe["direction"]),
    max_error=MUN_FLYBY_INCLINATION_ALIGNMENT_ERROR,
  ):
    record_mission_event(
      "mun_flyby_soi_periapsis_trim_alignment_failed",
      "Mun Flyby",
      direction=best_probe["label"],
      periapsis=read_current_periapsis(vessel),
    )
    set_rcs(vessel, False)
    return

  started_at = time.monotonic()
  previous_score = mun_soi_periapsis_score(read_current_periapsis(vessel))

  while time.monotonic() - started_at < MUN_FLYBY_SOI_PERIAPSIS_TRIM_MAX_SECONDS:
    guard.check()
    TLM.update("Adjusting Mun periapsis")
    periapsis = read_current_periapsis(vessel)
    score = mun_soi_periapsis_score(periapsis)

    if score is None:
      break

    if score <= MUN_FLYBY_SOI_PERIAPSIS_TOLERANCE:
      break

    if previous_score is not None and score > previous_score + 1000:
      break

    previous_score = score

    if not stage_if_needed(vessel):
      record_mission_event(
        "mun_flyby_soi_periapsis_no_thrust",
        "Mun Flyby",
        periapsis=periapsis,
      )
      break

    vessel.control.throttle = MUN_FLYBY_SOI_PERIAPSIS_TRIM_THROTTLE
    time.sleep(MUN_FLYBY_BURN_INTERVAL)

  vessel.control.throttle = 0
  final_periapsis = read_current_periapsis(vessel)
  record_mission_event(
    "mun_flyby_soi_periapsis_refine_done",
    "Mun Flyby",
    direction=best_probe["label"],
    periapsis=final_periapsis,
    target_periapsis=MUN_FLYBY_SOI_TARGET_PERIAPSIS,
    tolerance=MUN_FLYBY_SOI_PERIAPSIS_TOLERANCE,
    elapsed_seconds=time.monotonic() - started_at,
  )
  set_rcs(vessel, False)


def wait_for_mun_flyby_completion(conn, vessel, mun, plan, guard):
  kerbin = safe_value(lambda: vessel.orbit.body)
  kerbin_reference_frame = safe_value(lambda: kerbin.non_rotating_reference_frame)
  mun_soi = get_mun_sphere_of_influence(mun)
  started_ut = TLM.read("ut")
  deadline_ut = started_ut + max(plan["transfer_time"] * 1.75, 6 * 3600)
  encounter_started = False
  closest_distance = None

  record_mission_event(
    "mun_flyby_coast_start",
    "Mun Flyby",
    deadline_ut=deadline_ut,
    mun_sphere_of_influence=mun_soi,
    transfer_time=plan["transfer_time"],
    orbit_patch=read_orbit_patch(vessel),
    time_to_apoapsis=TLM.read("time_to_apoapsis"),
    apoapsis=TLM.read("apoapsis"),
    periapsis=TLM.read("periapsis"),
  )

  while TLM.read("ut") < deadline_ut:
    guard.check()
    body_name = safe_value(lambda: vessel.orbit.body.name)
    orbit_patch = read_orbit_patch(vessel)
    reference_frame = kerbin_reference_frame

    if body_name == "Mun":
      reference_frame = safe_value(lambda: mun.non_rotating_reference_frame, reference_frame)

    mun_distance = get_mun_distance(vessel, mun, reference_frame)

    if mun_distance is not None:
      closest_distance = (
        mun_distance
        if closest_distance is None
        else min(closest_distance, mun_distance)
      )

    if not encounter_started and body_name == "Mun":
      encounter_started = True
      stop_warp(conn)
      record_mission_event(
        "mun_flyby_soi_change_to_mun",
        "Mun Flyby",
        body=body_name,
        mun_distance=mun_distance,
        closest_distance=closest_distance,
        orbit_patch=orbit_patch,
        apoapsis=TLM.read("apoapsis"),
        periapsis=TLM.read("periapsis"),
      )
      refine_mun_soi_periapsis(conn, vessel, guard)

    if encounter_started:
      TLM.update("Flying by Mun")

      if body_name == "Kerbin" and mun_distance and mun_distance > mun_soi * 1.1:
        record_mission_event(
          "mun_flyby_soi_return_to_kerbin",
          "Mun Flyby",
          body=body_name,
          mun_distance=mun_distance,
          closest_distance=closest_distance,
          orbit_patch=orbit_patch,
          apoapsis=TLM.read("apoapsis"),
          periapsis=TLM.read("periapsis"),
        )
        record_mission_event(
          "mun_flyby_complete",
          "Mun Flyby",
          confirmed_by="orbit_body_soi_change",
          closest_distance=closest_distance,
        )
        return

      coast_seconds = 60
    else:
      TLM.update("Coasting to Mun encounter")
      time_to_apoapsis = TLM.read("time_to_apoapsis")

      if time_to_apoapsis > 3600:
        coast_seconds = min(1800, max(60, time_to_apoapsis - 1800))
      elif time_to_apoapsis > 900:
        coast_seconds = min(600, max(60, time_to_apoapsis - 600))
      elif time_to_apoapsis > 180:
        coast_seconds = min(120, max(30, time_to_apoapsis - 120))
      else:
        coast_seconds = 30

    record_mission_event(
      "mun_flyby_coast_progress",
      "Mun Flyby",
      body=body_name,
      mun_distance=mun_distance,
      closest_distance=closest_distance,
      orbit_patch=orbit_patch,
      time_to_apoapsis=TLM.read("time_to_apoapsis"),
      coast_seconds=coast_seconds,
    )
    coast_to_ut(
      conn,
      "Flying by Mun" if encounter_started else "Coasting to Mun encounter",
      TLM.read("ut") + coast_seconds,
      warp_factor=RAILS_WARP_FACTOR,
      guard=guard,
    )

  raise MissionAborted(
    "Mun flyby stopped because the vessel did not encounter Mun before the coast deadline"
  )


def circularize_at_apoapsis_with_session(conn, vessel, guard, phase="Apoapsis Circularize"):
  ensure_kerbin_orbit(vessel)

  if not orbit_needs_apoapsis_circularization():
    record_mission_event(
      "apoapsis_circularize_skipped",
      phase,
      apoapsis=TLM.read("apoapsis"),
      periapsis=TLM.read("periapsis"),
      tolerance=APOAPSIS_CIRCULARIZE_PERIAPSIS_TOLERANCE,
    )
    return

  if phase == "Mun Flyby" and not mun_flyby_needs_apoapsis_circularization():
    record_mission_event(
      "apoapsis_circularize_skipped",
      phase,
      apoapsis=TLM.read("apoapsis"),
      periapsis=TLM.read("periapsis"),
      tolerance=APOAPSIS_CIRCULARIZE_PERIAPSIS_TOLERANCE,
      minimum_mun_flyby_periapsis=MUN_FLYBY_APOAPSIS_CIRCULARIZE_MIN_PERIAPSIS,
    )
    return

  target_periapsis = max(
    CIRCULARIZATION_ATMOSPHERE_ALTITUDE,
    TLM.read("apoapsis") - APOAPSIS_CIRCULARIZE_PERIAPSIS_TOLERANCE,
  )
  apoapsis_ut = TLM.read("ut") + TLM.read("time_to_apoapsis")
  alignment_ut = max(
    TLM.read("ut"),
    apoapsis_ut - APOAPSIS_CIRCULARIZE_ALIGNMENT_BUFFER,
  )
  burn_start_ut = max(
    TLM.read("ut"),
    apoapsis_ut - APOAPSIS_CIRCULARIZE_LEAD_TIME,
  )
  record_mission_event(
    "apoapsis_circularize_plan",
    phase,
    target_periapsis=target_periapsis,
    periapsis=TLM.read("periapsis"),
    apoapsis=TLM.read("apoapsis"),
    time_to_apoapsis=TLM.read("time_to_apoapsis"),
    alignment_ut=alignment_ut,
    burn_start_ut=burn_start_ut,
  )

  coast_to_ut(
    conn,
    "Warping to apoapsis circularization",
    alignment_ut,
    warp_factor=RAILS_WARP_FACTOR,
    guard=guard,
  )

  set_rcs(vessel, True)
  record_mission_event(
    "apoapsis_circularize_rcs_enabled",
    phase,
    rcs=safe_value(lambda: vessel.control.rcs),
  )
  aim_orbital_prograde(vessel)
  record_mission_event(
    "apoapsis_circularize_alignment_start",
    phase,
    alignment_error=read_alignment_error(vessel),
    autopilot_error=read_autopilot_error(vessel),
  )

  if not wait_for_transfer_alignment(conn, vessel, guard):
    raise MissionAborted("Circularize at apoapsis stopped because prograde alignment did not settle")

  while TLM.read("ut") < burn_start_ut:
    guard.check()
    TLM.update("Waiting for apoapsis circularization")
    maintain_coast_warp(conn, allow_rails=False)
    time.sleep(0.1)

  stop_warp(conn)

  while TLM.read("periapsis") < target_periapsis:
    guard.check()
    TLM.update("Circularizing at apoapsis")
    alignment_error = read_alignment_error(vessel)

    if alignment_error is not None and alignment_error > 8:
      vessel.control.throttle = 0
      aim_orbital_prograde(vessel)
      if not wait_for_transfer_alignment(conn, vessel, guard):
        raise MissionAborted("Circularize at apoapsis stopped because prograde alignment was lost")

    set_apoapsis_circularization_throttle(
      vessel,
      target_periapsis - TLM.read("periapsis"),
    )

    if vessel.available_thrust < 0.1:
      current_stage = vessel.control.current_stage
      next_stage = current_stage - 1
      if stage_has_engine(vessel, next_stage):
        vessel.control.activate_next_stage()
      else:
        raise MissionAborted("Circularize at apoapsis stopped because the vessel ran out of thrust")

    time.sleep(MUN_FLYBY_BURN_INTERVAL)

  vessel.control.throttle = 0
  record_mission_event(
    "apoapsis_circularize_done",
    phase,
    apoapsis=TLM.read("apoapsis"),
    periapsis=TLM.read("periapsis"),
    target_periapsis=target_periapsis,
  )
  set_rcs(vessel, False)
  record_mission_event(
    "apoapsis_circularize_rcs_disabled",
    phase,
    rcs=safe_value(lambda: vessel.control.rcs),
  )
  TLM.update("Circularized at apoapsis")


def circularize_at_apoapsis():
  record_mission_event("apoapsis_circularize_enter", "Apoapsis Circularize")
  conn, vessel = safe_connect("Apoapsis Circularize")

  if not conn:
    record_mission_event("apoapsis_circularize_no_connection", "Apoapsis Circularize")
    raise MissionAborted("Circularize at apoapsis stopped because no active vessel is available")

  register_mission_connection(conn, vessel, "Apoapsis Circularize")
  guard = MissionGuard(conn, vessel, "Apoapsis Circularize")

  try:
    TLM.begin(conn, vessel)
    circularize_at_apoapsis_with_session(conn, vessel, guard)
  except Exception as error:
    record_mission_event("apoapsis_circularize_error", "Apoapsis Circularize", error=str(error))
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Apoapsis Circularize")) from error
    raise
  finally:
    vessel.control.throttle = 0
    set_rcs(vessel, False)
    record_mission_event("apoapsis_circularize_close", "Apoapsis Circularize")
    close_mission_connection(conn)


def flyby_mun():
  record_mission_event("mun_flyby_enter", "Mun Flyby")
  conn, vessel, guard = connect_mun_flyby_session()

  try:
    if not is_stable_kerbin_orbit(vessel):
      if not is_launch_ready(vessel):
        ensure_kerbin_orbit(vessel)

      record_mission_event("mun_flyby_launch_start", "Mun Flyby")
      close_mission_connection(conn)
      conn = None

      if not launch_to_orbit():
        raise MissionAborted("Mun flyby stopped because launch to orbit did not complete")

      record_mission_event("mun_flyby_launch_done", "Mun Flyby")
      conn, vessel, guard = connect_mun_flyby_session()

    ensure_kerbin_orbit(vessel)
    record_mission_event(
      "mun_flyby_apoapsis_circularize_skipped",
      "Mun Flyby",
      apoapsis=TLM.read("apoapsis"),
      periapsis=TLM.read("periapsis"),
    )
    mun = get_body(conn, "Mun")

    if mun is None:
      raise MissionAborted("Mun flyby stopped because Mun body data is unavailable")

    trim_mun_inclination(conn, vessel, mun, guard)
    plan = calculate_mun_transfer_plan(vessel, mun)
    record_mission_event("mun_flyby_plan", "Mun Flyby", **plan)

    if TLM.read("apoapsis") >= plan["cutoff_apoapsis"]:
      orbit_intercept = estimate_mun_orbit_intercept(vessel, mun, plan)
      record_mission_event(
        "mun_flyby_existing_transfer_check",
        "Mun Flyby",
        apoapsis=TLM.read("apoapsis"),
        periapsis=TLM.read("periapsis"),
        cutoff_apoapsis=plan["cutoff_apoapsis"],
        max_apoapsis=plan["max_apoapsis"],
        **orbit_intercept,
      )

      if orbit_intercept.get("orbit_intercept"):
        wait_for_mun_flyby_completion(conn, vessel, mun, plan, guard)
        TLM.update("Mun flyby complete")
        return

    wait_for_mun_phase(conn, vessel, mun, plan, guard)
    perform_mun_injection_burn(conn, vessel, mun, plan, guard)
    wait_for_mun_flyby_completion(conn, vessel, mun, plan, guard)
    TLM.update("Mun flyby complete")
  except Exception as error:
    record_mission_event("mun_flyby_error", "Mun Flyby", error=str(error))
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Mun Flyby")) from error
    raise
  finally:
    if vessel:
      vessel.control.throttle = 0
      set_rcs(vessel, False)
    record_mission_event("mun_flyby_close", "Mun Flyby")
    if conn:
      close_mission_connection(conn)


def circularize_at_periapsis():
  record_mission_event("periapsis_circularize_enter", "Periapsis Circularize")
  conn, vessel = safe_connect("Periapsis Circularize")

  if not conn:
    record_mission_event("periapsis_circularize_no_connection", "Periapsis Circularize")
    raise MissionAborted("Circularize at periapsis stopped because no active vessel is available")

  register_mission_connection(conn, vessel, "Periapsis Circularize")
  guard = MissionGuard(conn, vessel, "Periapsis Circularize")

  try:
    TLM.begin(conn, vessel)
    ensure_kerbin_orbit(vessel)

    target_apoapsis = max(
      CIRCULARIZATION_ATMOSPHERE_ALTITUDE,
      TLM.read("periapsis") + PERIAPSIS_CIRCULARIZE_APOAPSIS_TOLERANCE,
    )
    periapsis_ut = TLM.read("ut") + TLM.read("time_to_periapsis")
    alignment_ut = max(
      TLM.read("ut"),
      periapsis_ut - PERIAPSIS_CIRCULARIZE_ALIGNMENT_BUFFER,
    )
    burn_start_ut = max(
      TLM.read("ut"),
      periapsis_ut - PERIAPSIS_CIRCULARIZE_LEAD_TIME,
    )
    record_mission_event(
      "periapsis_circularize_plan",
      "Periapsis Circularize",
      target_apoapsis=target_apoapsis,
      periapsis=TLM.read("periapsis"),
      apoapsis=TLM.read("apoapsis"),
      time_to_periapsis=TLM.read("time_to_periapsis"),
      alignment_ut=alignment_ut,
      burn_start_ut=burn_start_ut,
    )

    coast_to_ut(
      conn,
      "Warping to periapsis circularization",
      alignment_ut,
      warp_factor=RAILS_WARP_FACTOR,
      guard=guard,
    )

    set_rcs(vessel, True)
    record_mission_event(
      "periapsis_circularize_rcs_enabled",
      "Periapsis Circularize",
      rcs=safe_value(lambda: vessel.control.rcs),
    )
    aim_orbital_retrograde(vessel)
    record_mission_event(
      "periapsis_circularize_alignment_start",
      "Periapsis Circularize",
      alignment_error=read_alignment_error(vessel),
      autopilot_error=read_autopilot_error(vessel),
    )

    if not wait_for_transfer_alignment(
      conn,
      vessel,
      guard,
      alignment_reader=lambda: read_autopilot_abs_error(vessel),
    ):
      raise MissionAborted("Circularize at periapsis stopped because retrograde alignment did not settle")

    while TLM.read("ut") < burn_start_ut:
      guard.check()
      TLM.update("Waiting for periapsis circularization")
      maintain_coast_warp(conn, allow_rails=False)
      time.sleep(0.1)

    stop_warp(conn)

    while TLM.read("apoapsis") > target_apoapsis:
      guard.check()
      TLM.update("Circularizing at periapsis")
      alignment_error = read_alignment_error(vessel)

      if alignment_error is not None and alignment_error > 8:
        vessel.control.throttle = 0
        aim_orbital_retrograde(vessel)
        if not wait_for_transfer_alignment(
          conn,
          vessel,
          guard,
          alignment_reader=lambda: read_autopilot_abs_error(vessel),
        ):
          raise MissionAborted("Circularize at periapsis stopped because retrograde alignment was lost")

      set_periapsis_circularization_throttle(
        vessel,
        TLM.read("apoapsis") - target_apoapsis,
      )

      if vessel.available_thrust < 0.1:
        current_stage = vessel.control.current_stage
        next_stage = current_stage - 1
        if stage_has_engine(vessel, next_stage):
          vessel.control.activate_next_stage()
        else:
          raise MissionAborted("Circularize at periapsis stopped because the vessel ran out of thrust")

      time.sleep(MUN_FLYBY_BURN_INTERVAL)

    vessel.control.throttle = 0
    record_mission_event(
      "periapsis_circularize_done",
      "Periapsis Circularize",
      apoapsis=TLM.read("apoapsis"),
      periapsis=TLM.read("periapsis"),
      target_apoapsis=target_apoapsis,
    )
    set_rcs(vessel, False)
    record_mission_event(
      "periapsis_circularize_rcs_disabled",
      "Periapsis Circularize",
      rcs=safe_value(lambda: vessel.control.rcs),
    )
    TLM.update("Circularized at periapsis")
  except Exception as error:
    record_mission_event("periapsis_circularize_error", "Periapsis Circularize", error=str(error))
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Periapsis Circularize")) from error
    raise
  finally:
    vessel.control.throttle = 0
    set_rcs(vessel, False)
    record_mission_event("periapsis_circularize_close", "Periapsis Circularize")
    close_mission_connection(conn)
