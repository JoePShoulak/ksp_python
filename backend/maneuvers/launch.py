import krpc # type: ignore
import math
import threading
import time
from telemetry import TLM

########## Helpers

ACTIVE_MISSION_LOCK = threading.Lock()
ACTIVE_MISSION = None
MISSION_WATCHDOG_INTERVAL = 0.5
MET_ROLLBACK_TOLERANCE = 0.25

class MissionAborted(RuntimeError):
  pass


def is_vessel_lost_error(error):
  return "No such vessel" in str(error)


def mission_aborted_message(phase):
  return f"{phase} stopped because the active vessel is no longer available"


def get_vessel_identifier(vessel):
  try:
    return vessel.id
  except Exception:
    return None


def read_vessel_met(vessel):
  try:
    met = vessel.met
  except Exception:
    return None

  if met is None:
    return None

  return float(met)


def get_scene_name(conn):
  try:
    current_scene = conn.space_center.current_game_scene
  except Exception:
    return "unknown"

  return str(current_scene)


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


def safe_connect(name):
  try:
    conn = krpc.connect(name=name)
  except Exception:
    print("!== Error making connection. Is there a reachable kRPC running in KSP? ==!")
    return False, False

  try:
    vessel = conn.space_center.active_vessel
  except Exception:
    conn.close()
    print("!== Error finding an active vessel in KSP. ==!")
    return False, False

  if not vessel:
    conn.close()
    print("!== No active vessel in KSP. ==!")
    return False, False

  if not vessel_is_readable(vessel):
    scene_name = get_scene_name(conn)
    conn.close()
    print(f"!== Active vessel is not readable for telemetry. Scene: {scene_name} ==!")
    return False, False

  return conn, vessel


def stop_warp(conn):
  try:
    conn.space_center.rails_warp_factor = 0
    conn.space_center.physics_warp_factor = 0
  except Exception:
    pass


def close_connection(conn, stop_warp_first=True):
  if not conn:
    return

  try:
    if stop_warp_first:
      stop_warp(conn)
  finally:
    try:
      conn.close()
    except Exception:
      pass


def close_mission_connection(conn):
  close_connection(conn)
  TLM.reset()
  unregister_mission_connection(conn)


def force_close_mission_connection(conn):
  close_connection(conn, stop_warp_first=False)
  TLM.reset()


def ensure_vessel_available(vessel, phase):
  if not vessel_is_readable(vessel):
    raise MissionAborted(mission_aborted_message(phase))


def register_mission_connection(conn, vessel, phase):
  global ACTIVE_MISSION

  mission = {
    "conn": conn,
    "vessel": vessel,
    "phase": phase,
    "vessel_id": get_vessel_identifier(vessel),
    "last_met": read_vessel_met(vessel),
    "abort_requested": False,
  }

  with ACTIVE_MISSION_LOCK:
    ACTIVE_MISSION = mission

  watchdog = threading.Thread(
    target=watch_active_mission,
    args=(conn,),
    daemon=True,
    name=f"ksp-{phase.lower()}-watchdog",
  )
  watchdog.start()


def unregister_mission_connection(conn):
  global ACTIVE_MISSION

  with ACTIVE_MISSION_LOCK:
    if ACTIVE_MISSION and ACTIVE_MISSION["conn"] is conn:
      ACTIVE_MISSION = None


def get_registered_mission():
  with ACTIVE_MISSION_LOCK:
    return ACTIVE_MISSION


def is_registered_mission(conn):
  with ACTIVE_MISSION_LOCK:
    return bool(ACTIVE_MISSION and ACTIVE_MISSION["conn"] is conn)


def mission_abort_was_requested(conn):
  with ACTIVE_MISSION_LOCK:
    return bool(
      ACTIVE_MISSION
      and ACTIVE_MISSION["conn"] is conn
      and ACTIVE_MISSION["abort_requested"]
    )


def abort_active_mission(reason="Mission stopped"):
  global ACTIVE_MISSION

  with ACTIVE_MISSION_LOCK:
    mission = ACTIVE_MISSION

    if mission:
      mission["abort_requested"] = True
      ACTIVE_MISSION = None

  if not mission:
    return False

  print(f"!== {reason}; closing {mission['phase']} connection ==!")
  force_close_mission_connection(mission["conn"])
  return True


def abort_active_mission_if_stale(active_vessel):
  mission = get_registered_mission()

  if not mission:
    return False

  if not active_vessel or not vessel_is_readable(active_vessel):
    return abort_active_mission("Active vessel disappeared")

  active_vessel_id = get_vessel_identifier(active_vessel)
  mission_vessel_id = mission["vessel_id"]

  if mission_vessel_id and active_vessel_id and active_vessel_id != mission_vessel_id:
    return abort_active_mission("Active vessel changed")

  return abort_active_mission_if_met_rolled_back(active_vessel, "Active vessel MET rolled back")


def abort_active_mission_if_met_rolled_back(vessel, reason):
  mission = get_registered_mission()

  if not mission:
    return False

  current_met = read_vessel_met(vessel)
  last_met = mission["last_met"]

  if current_met is None:
    return False

  if last_met is not None and current_met + MET_ROLLBACK_TOLERANCE < last_met:
    return abort_active_mission(reason)

  with ACTIVE_MISSION_LOCK:
    if ACTIVE_MISSION and ACTIVE_MISSION["conn"] is mission["conn"]:
      ACTIVE_MISSION["last_met"] = max(
        current_met,
        ACTIVE_MISSION["last_met"] if ACTIVE_MISSION["last_met"] is not None else current_met,
      )

  return False


def validate_active_mission():
  mission = get_registered_mission()

  if not mission:
    return False

  if mission["abort_requested"]:
    abort_active_mission("Mission abort requested")
    return False

  mission_vessel = mission["vessel"]

  if not vessel_is_readable(mission_vessel):
    abort_active_mission("Mission vessel is no longer readable")
    return False

  try:
    active_vessel = mission["conn"].space_center.active_vessel
  except Exception:
    abort_active_mission("Mission connection can no longer reach an active vessel")
    return False

  if not active_vessel or not vessel_is_readable(active_vessel):
    abort_active_mission("Mission connection has no active vessel")
    return False

  if abort_active_mission_if_met_rolled_back(
    active_vessel,
    "Mission MET rolled back; assuming flight was reverted",
  ):
    return False

  mission_vessel_id = mission["vessel_id"]
  active_vessel_id = get_vessel_identifier(active_vessel)

  if mission_vessel_id and active_vessel_id and mission_vessel_id != active_vessel_id:
    abort_active_mission("Mission active vessel changed")
    return False

  return True


def watch_active_mission(conn):
  while is_registered_mission(conn):
    time.sleep(MISSION_WATCHDOG_INTERVAL)

    if not is_registered_mission(conn):
      return

    validate_active_mission()


def get_active_mission_status():
  if not validate_active_mission():
    return {
      "active": False,
      "phase": None,
    }

  mission = get_registered_mission()

  return {
    "active": True,
    "phase": mission["phase"],
  }


class MissionGuard:
  def __init__(self, conn, vessel, phase, check_interval=0.25):
    self.conn = conn
    self.vessel = vessel
    self.phase = phase
    self.check_interval = check_interval
    self.last_check = 0
    self.vessel_id = get_vessel_identifier(vessel)
    self.last_met = read_vessel_met(vessel)

  def check_met(self, vessel):
    current_met = read_vessel_met(vessel)

    if current_met is None:
      return

    if self.last_met is not None and current_met + MET_ROLLBACK_TOLERANCE < self.last_met:
      abort_active_mission("Mission MET rolled back; assuming flight was reverted")
      raise MissionAborted(mission_aborted_message(self.phase))

    self.last_met = max(current_met, self.last_met if self.last_met is not None else current_met)

  def check(self, force=False):
    if mission_abort_was_requested(self.conn):
      raise MissionAborted(mission_aborted_message(self.phase))

    now = time.monotonic()

    if not force and now - self.last_check < self.check_interval:
      return

    self.last_check = now
    ensure_vessel_available(self.vessel, self.phase)

    try:
      active_vessel = self.conn.space_center.active_vessel
    except Exception as error:
      raise MissionAborted(mission_aborted_message(self.phase)) from error

    if not active_vessel or not vessel_is_readable(active_vessel):
      raise MissionAborted(mission_aborted_message(self.phase))

    self.check_met(active_vessel)
    active_vessel_id = get_vessel_identifier(active_vessel)

    if self.vessel_id and active_vessel_id and active_vessel_id != self.vessel_id:
      raise MissionAborted(mission_aborted_message(self.phase))


def get_current_warp_factor(conn):
  return max(
    conn.space_center.rails_warp_factor,
    conn.space_center.physics_warp_factor,
  )


def manual_rails_warp_until(
  conn,
  status,
  stop_condition,
  warp_factor=5,
  update_interval=0.1,
  abort_condition=None,
  guard=None,
):
  max_warp = conn.space_center.maximum_rails_warp_factor
  selected_warp = min(warp_factor, max_warp)

  if abort_condition is None:
    abort_condition = lambda: False

  try:
    while not stop_condition() and not abort_condition():
      if guard:
        guard.check()

      TLM.update(status)

      if selected_warp > 0 and get_current_warp_factor(conn) <= 0:
        try:
          conn.space_center.rails_warp_factor = selected_warp
        except Exception:
          pass

      time.sleep(update_interval)

  finally:
    stop_warp(conn)


def wait_one_hour():
  conn, vessel = safe_connect("Wait")
  if not conn:
    raise MissionAborted("Wait stopped because no active vessel is available")

  register_mission_connection(conn, vessel, "Wait")
  guard = MissionGuard(conn, vessel, "Wait")

  try:
    guard.check(force=True)
    TLM.begin(conn, vessel)

    target_ut = TLM.read("ut") + 60 * 60

    manual_rails_warp_until(
      conn,
      "Warping for one hour",
      lambda: TLM.read("ut") >= target_ut,
      warp_factor=5,
      guard=guard,
    )

    TLM.update("One hour elapsed")
  except Exception as error:
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Wait")) from error
    raise
  finally:
    close_mission_connection(conn)


def vessel_is_down(vessel):
  return vessel.situation in (
    vessel.situation.landed,
    vessel.situation.splashed,
  )


def stage_has_engine(vessel, stage_number):
  return any(
    engine.part.stage == stage_number
    for engine in vessel.parts.engines
  )


def estimate_full_throttle_burn_time(vessel):
  propellant_requirements = {}

  active_engines = [
    engine
    for engine in vessel.parts.engines
    if engine.active and engine.available_thrust > 0
  ]

  for engine in active_engines:
    for propellant in engine.propellants:
      if propellant.current_requirement <= 0:
        continue

      if propellant.name not in propellant_requirements:
        propellant_requirements[propellant.name] = {
          "available": propellant.total_resource_available,
          "required": 0,
        }

      propellant_requirements[propellant.name]["required"] += propellant.current_requirement

  burn_times = [
    data["available"] / data["required"]
    for data in propellant_requirements.values()
    if data["required"] > 0
  ]

  if not burn_times:
    return 0

  return min(burn_times)

########## Mini-Maneuvers

def launch(conn, vessel, guard):
  guard.check(force=True)
  TLM.update("Pre-flight check")
  vessel.control.sas = False
  vessel.control.rcs = False
  vessel.control.throttle = 1.0

  for status in ("Pre-flight check", "Launching in 3...", "Launching in 2...", "Launching in 1..."):
    TLM.update(status)
    time.sleep(1)
    guard.check(force=True)

  vessel.control.activate_next_stage()
  guard.check(force=True)
  vessel.auto_pilot.engage()
  vessel.auto_pilot.target_pitch_and_heading(90, 90)
  vessel.auto_pilot.target_roll = 0

  while TLM.read("altitude") < 1000:
    guard.check()
    TLM.update("Vertical Ascent")
    time.sleep(0.1)


def gravity_turn_to_orbit(conn, vessel, guard):
  guard.check(force=True)
  TLM.update("Pitch over")
  vessel.auto_pilot.target_pitch_and_heading(75, 90)

  for _ in range(70):
    time.sleep(0.1)
    guard.check()

  vessel.auto_pilot.reference_frame = vessel.surface_velocity_reference_frame
  vessel.auto_pilot.target_direction = (0, 1, 0)
  vessel.auto_pilot.target_roll = 0

  while TLM.read("apoapsis") < 80000:
    guard.check()
    TLM.update("Staging to space")

    current_stage = vessel.control.current_stage
    next_stage = current_stage - 1

    if vessel.available_thrust < 0.1 and stage_has_engine(vessel, next_stage):
      vessel.control.activate_next_stage()

    time.sleep(0.1)

  vessel.control.throttle = 0

# TODO: Fix this warp and autopilot mess
def circularize(conn, vessel, guard):
  guard.check(force=True)
  while TLM.read("altitude") < 70000:
    guard.check()
    TLM.update("Waiting to circularize")
    time.sleep(0.01)

  guard.check(force=True)
  vessel.auto_pilot.target_direction = (0, 1, 0)
  vessel.auto_pilot.disengage()

  circularization_start_ut = (
    TLM.read("ut") +
    vessel.orbit.time_to_apoapsis -
    10
  )

  # manual_rails_warp_until(
  #   conn,
  #   "Warping to circularization",
  #   lambda: TLM.read("ut") >= circularization_start_ut,
  #   warp_factor=2,
  # )

  time.sleep(0.5)
  guard.check(force=True)
  print("Beginning to aim prograde")
  vessel.auto_pilot.target_direction = (0, 1, 0)
  vessel.auto_pilot.engage()
  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
  # while vessel.auto_pilot.error > 1: time.sleep(0.001)
  # vessel.auto_pilot.wait()
  while TLM.read("ut") < circularization_start_ut:
    guard.check()
    TLM.update("Waiting to Circularize")
    time.sleep(0.01)
  guard.check(force=True)
  vessel.control.throttle = 1

  while TLM.read("periapsis") < 77500:
    guard.check()
    TLM.update("Circularizing")

    current_stage = vessel.control.current_stage
    next_stage = current_stage - 1

    if vessel.available_thrust < 0.1:
      if stage_has_engine(vessel, next_stage):
        vessel.control.activate_next_stage()
      elif TLM.read("periapsis") < 70000:
        TLM.update("Orbit failed")
        vessel.control.throttle = 0
        for _ in range(30):
          time.sleep(0.1)
          guard.check()
        return suborbital_landing()

    time.sleep(0.01)

  guard.check(force=True)
  vessel.control.throttle = 0

########## Maneuvers
def suborbital_landing():
  conn, vessel = safe_connect("Launch")
  if not conn:
    raise MissionAborted("Suborbital landing stopped because no active vessel is available")

  register_mission_connection(conn, vessel, "Suborbital landing")
  guard = MissionGuard(conn, vessel, "Suborbital landing")

  try:
    guard.check(force=True)
    TLM.begin(conn, vessel)
    TLM.update("Preparing suborbital landing")

    while vessel.control.current_stage > 0:
      guard.check()
      TLM.update("Dumping remaining stages")
      vessel.control.activate_next_stage()
      time.sleep(0.1)

    guard.check(force=True)
    vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
    vessel.auto_pilot.target_direction = (0, -1, 0)

    TLM.update("Suborbital landing configured")
  except Exception as error:
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Suborbital landing")) from error
    raise
  finally:
    close_mission_connection(conn)


def launch_to_orbit():
  conn, vessel = safe_connect("Launch")
  if not conn:
    raise MissionAborted("Launch stopped because no active vessel is available")

  register_mission_connection(conn, vessel, "Launch")
  guard = MissionGuard(conn, vessel, "Launch")

  try:
    guard.check(force=True)
    TLM.begin(conn, vessel)

    launch(conn, vessel, guard)
    gravity_turn_to_orbit(conn, vessel, guard)
    circularize(conn, vessel, guard)

    TLM.update("Orbit achieved!")
  except Exception as error:
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Launch")) from error
    raise
  finally:
    close_mission_connection(conn)


def land_rocket():
  conn, vessel = safe_connect("Land")
  if not conn:
    raise MissionAborted("Land stopped because no active vessel is available")

  register_mission_connection(conn, vessel, "Land")
  guard = MissionGuard(conn, vessel, "Land")

  try:
    guard.check(force=True)
    TLM.begin(conn, vessel)

    atmosphere_altitude = 70000
    deorbit_periapsis = 55000

    TLM.update("Preparing deorbit burn")

    vessel.auto_pilot.engage()
    vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame

    apoapsis_arrival_ut = TLM.read("ut") + TLM.read("time_to_apoapsis")

    manual_rails_warp_until(
      conn,
      "Warping to apoapsis",
      lambda: TLM.read("ut") >= apoapsis_arrival_ut,
      warp_factor=5,
      guard=guard,
    )

    guard.check(force=True)
    TLM.update("Pointing retrograde")
    vessel.auto_pilot.target_direction = (0, -1, 0)
    vessel.auto_pilot.wait()

    TLM.update("Lowering periapsis")
    vessel.control.throttle = 0.1

    while TLM.read("periapsis") > deorbit_periapsis:
      guard.check()
      TLM.update("Lowering periapsis")
      time.sleep(0.1)

    guard.check(force=True)
    vessel.control.throttle = 0.0

    manual_rails_warp_until(
      conn,
      "Warping to atmosphere",
      lambda: TLM.read("altitude") <= atmosphere_altitude,
      warp_factor=5,
      abort_condition=lambda: TLM.read("altitude") <= atmosphere_altitude,
      guard=guard,
    )

    TLM.update("Entering atmosphere")

    TLM.update("Burning remaining fuel")
    vessel.auto_pilot.target_direction = (0, -1, 0)
    vessel.control.throttle = 1.0

    while TLM.read("liquid_fuel") > 0.1:
      guard.check()
      TLM.update("Burning remaining fuel")

      if vessel.control.throttle < 1.0:
        vessel.control.throttle = 1.0

      time.sleep(0.1)

    guard.check(force=True)
    vessel.control.throttle = 0.0

    TLM.update("Dumping engines")
    vessel.control.activate_next_stage()

    while TLM.read("altitude") > 5000:
      guard.check()
      TLM.update("Waiting to deploy parachutes")
      time.sleep(0.1)

    guard.check(force=True)
    TLM.update("Deploying parachutes")
    vessel.control.activate_next_stage()

    while not vessel_is_down(vessel):
      guard.check()
      TLM.update("Descending under parachutes")
      time.sleep(0.1)

    TLM.update("Landed")
  except Exception as error:
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Land")) from error
    raise
  finally:
    close_mission_connection(conn)


def lko_tourism():
  launch_to_orbit()
  wait_one_hour()
  land_rocket()
