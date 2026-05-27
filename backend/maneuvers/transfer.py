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
  MUN_FLYBY_APOAPSIS_MARGIN,
  MUN_FLYBY_BURN_INTERVAL,
  MUN_FLYBY_COARSE_THROTTLE,
  MUN_FLYBY_FINE_THROTTLE,
  MUN_FLYBY_MAX_WAIT_SECONDS,
  MUN_FLYBY_MEDIUM_THROTTLE,
  MUN_FLYBY_PHASE_TOLERANCE,
  MUN_FLYBY_TARGET_PERIAPSIS,
  PERIAPSIS_CIRCULARIZE_ALIGNMENT_BUFFER,
  PERIAPSIS_CIRCULARIZE_APOAPSIS_TOLERANCE,
  PERIAPSIS_CIRCULARIZE_COARSE_THROTTLE,
  PERIAPSIS_CIRCULARIZE_FINE_THROTTLE,
  PERIAPSIS_CIRCULARIZE_LEAD_TIME,
  PERIAPSIS_CIRCULARIZE_MEDIUM_THROTTLE,
  RAILS_WARP_FACTOR,
)
from .control import coast_to_ut, maintain_coast_warp, read_autopilot_error, warp_to_ut
from .vessel import stage_has_engine


def vector_magnitude(vector):
  return math.sqrt(sum(component * component for component in vector))


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
    180 - math.degrees(mun_mean_motion * transfer_time)
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
    "transfer_time": transfer_time,
    "lead_angle": lead_angle,
    "estimated_delta_v": max(0, transfer_periapsis_speed - circular_speed),
  }


def get_body(conn, name):
  return safe_value(lambda: conn.space_center.bodies[name])


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

  return 360 / vessel_period - 360 / target_period


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
  started_at = time.monotonic()
  phase_rate = estimate_phase_rate_degrees_per_second(vessel, mun)

  while True:
    guard.check()
    TLM.update("Waiting for Mun transfer window")
    phase_angle = signed_phase_angle_degrees(vessel, mun, reference_frame)

    if phase_angle is None:
      raise MissionAborted("Mun flyby stopped because phase angle could not be measured")

    phase_error = normalize_angle_degrees(phase_angle - plan["lead_angle"])

    if abs(phase_error) <= MUN_FLYBY_PHASE_TOLERANCE:
      stop_warp(conn)
      record_mission_event(
        "mun_flyby_phase_ready",
        "Mun Flyby",
        phase_angle=phase_angle,
        phase_error=phase_error,
        target_phase_angle=plan["lead_angle"],
      )
      return

    if time.monotonic() - started_at > MUN_FLYBY_MAX_WAIT_SECONDS:
      raise MissionAborted("Mun flyby stopped because the transfer window did not arrive")

    record_mission_event(
      "mun_flyby_phase_wait",
      "Mun Flyby",
      phase_angle=phase_angle,
      phase_error=phase_error,
      target_phase_angle=plan["lead_angle"],
      phase_rate=phase_rate,
    )
    seconds_until_target = seconds_to_phase_target(phase_error, phase_rate)

    if seconds_until_target is None:
      coast_seconds = min(120, max(5, abs(phase_error) * 8))
    elif seconds_until_target > 90:
      coast_seconds = max(5, seconds_until_target - 45)
    elif seconds_until_target > 20:
      coast_seconds = max(1, seconds_until_target - 8)
    else:
      coast_seconds = min(2, max(0.25, seconds_until_target / 2))

    if seconds_until_target is not None and seconds_until_target > 20:
      warp_to_ut(
        conn,
        "Waiting for Mun transfer window",
        TLM.read("ut") + coast_seconds,
        warp_factor=RAILS_WARP_FACTOR,
        guard=guard,
      )
    else:
      coast_to_ut(
        conn,
        "Waiting for Mun transfer window",
        TLM.read("ut") + coast_seconds,
        warp_factor=RAILS_WARP_FACTOR,
        guard=guard,
      )


def wait_for_transfer_alignment(conn, vessel, guard, alignment_reader=None):
  if alignment_reader is None:
    alignment_reader = lambda: read_alignment_error(vessel)

  started_at = time.monotonic()
  stable_since = None

  try:
    while time.monotonic() - started_at < MUN_FLYBY_ALIGNMENT_TIMEOUT:
      now = time.monotonic()
      guard.check()
      TLM.update("Aiming for Mun transfer")
      error = alignment_reader()

      if error is None:
        return False

      if error <= AUTOPILOT_ALIGNMENT_ERROR:
        if stable_since is None:
          stable_since = now

        if now - stable_since >= 0.75:
          return True
      else:
        stable_since = None

      maintain_coast_warp(conn, allow_rails=False)
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


def aim_orbital_retrograde(vessel):
  vessel.auto_pilot.engage()
  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
  vessel.auto_pilot.target_direction = (0, -1, 0)
  vessel.auto_pilot.target_roll = 0


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


def perform_mun_injection_burn(conn, vessel, plan, guard):
  aim_orbital_prograde(vessel)
  record_mission_event(
    "mun_flyby_alignment_start",
    "Mun Flyby",
    alignment_error=read_alignment_error(vessel),
    autopilot_error=read_autopilot_error(vessel),
  )

  if not wait_for_transfer_alignment(conn, vessel, guard):
    record_mission_event(
      "mun_flyby_alignment_failed",
      "Mun Flyby",
      alignment_error=read_alignment_error(vessel),
      autopilot_error=read_autopilot_error(vessel),
    )
    raise MissionAborted("Mun flyby stopped because prograde alignment did not settle")

  record_mission_event(
    "mun_flyby_alignment_done",
    "Mun Flyby",
    alignment_error=read_alignment_error(vessel),
    autopilot_error=read_autopilot_error(vessel),
  )

  while TLM.read("apoapsis") < plan["target_apoapsis"]:
    guard.check()
    TLM.update("Burning for Mun flyby")

    alignment_error = read_alignment_error(vessel)
    if alignment_error is not None and alignment_error > 8:
      vessel.control.throttle = 0
      record_mission_event(
        "mun_flyby_alignment_lost",
        "Mun Flyby",
        alignment_error=alignment_error,
        apoapsis=TLM.read("apoapsis"),
      )
      aim_orbital_prograde(vessel)
      if not wait_for_transfer_alignment(conn, vessel, guard):
        raise MissionAborted("Mun flyby stopped because prograde alignment was lost")

    apoapsis_remaining = plan["target_apoapsis"] - TLM.read("apoapsis")
    set_transfer_throttle(vessel, apoapsis_remaining)

    if TLM.read("apoapsis") >= plan["cutoff_apoapsis"]:
      break

    if vessel.available_thrust < 0.1:
      current_stage = vessel.control.current_stage
      next_stage = current_stage - 1
      if stage_has_engine(vessel, next_stage):
        vessel.control.activate_next_stage()
      else:
        raise MissionAborted("Mun flyby stopped because the vessel ran out of thrust")

    time.sleep(MUN_FLYBY_BURN_INTERVAL)

  vessel.control.throttle = 0
  record_mission_event(
    "mun_flyby_injection_done",
    "Mun Flyby",
    apoapsis=TLM.read("apoapsis"),
    periapsis=TLM.read("periapsis"),
    target_apoapsis=plan["target_apoapsis"],
    target_mun_periapsis=plan["target_periapsis"],
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
    circularize_at_apoapsis_with_session(conn, vessel, guard, phase="Mun Flyby")
    mun = get_body(conn, "Mun")

    if mun is None:
      raise MissionAborted("Mun flyby stopped because Mun body data is unavailable")

    plan = calculate_mun_transfer_plan(vessel, mun)
    record_mission_event("mun_flyby_plan", "Mun Flyby", **plan)
    wait_for_mun_phase(conn, vessel, mun, plan, guard)
    perform_mun_injection_burn(conn, vessel, plan, guard)
    TLM.update("Mun flyby transfer set")
  except Exception as error:
    record_mission_event("mun_flyby_error", "Mun Flyby", error=str(error))
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Mun Flyby")) from error
    raise
  finally:
    if vessel:
      vessel.control.throttle = 0
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
    TLM.update("Circularized at periapsis")
  except Exception as error:
    record_mission_event("periapsis_circularize_error", "Periapsis Circularize", error=str(error))
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Periapsis Circularize")) from error
    raise
  finally:
    vessel.control.throttle = 0
    record_mission_event("periapsis_circularize_close", "Periapsis Circularize")
    close_mission_connection(conn)
