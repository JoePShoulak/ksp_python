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

from .constants import (
  AUTOPILOT_ALIGNMENT_ERROR,
  LANDING_ATMOSPHERE_ALTITUDE,
  LANDING_DEORBIT_ALIGNMENT_BUFFER,
  LANDING_DEORBIT_BURN_LEAD_TIME,
  LANDING_DEORBIT_DRIFT_ERROR,
  LANDING_DEORBIT_PERIAPSIS,
  LANDING_DEORBIT_PROGRESS_MIN_DROP,
  LANDING_DEORBIT_PROGRESS_TIMEOUT,
  LANDING_DEORBIT_THROTTLE,
  LANDING_SPEED_DUMP_ALIGNMENT_TIMEOUT,
  LANDING_SPEED_DUMP_MIN_APOAPSIS,
  LANDING_SPEED_DUMP_START_ALTITUDE,
  PARACHUTE_DEPLOY_ALTITUDE,
  RAILS_WARP_FACTOR,
)
from .control import (
  maintain_coast_warp,
  maintain_physics_warp,
  manual_rails_warp_until,
  manual_physics_warp_until,
  rails_warp_to_atmosphere,
  read_autopilot_error,
  wait_for_autopilot_alignment,
)
from .vessel import (
  engine_uses_resource,
  has_usable_thrust,
  stage_has_engine,
  vessel_is_down,
)

def configure_suborbital_landing(conn, vessel, guard, dump_stages=False):
  TLM.update("Preparing suborbital landing")
  stop_warp(conn)
  vessel.control.throttle = 0

  if dump_stages:
    while vessel.control.current_stage > 0:
      guard.check()
      vessel.control.throttle = 0
      TLM.update("Dumping remaining stages")
      vessel.control.activate_next_stage()
      time.sleep(0.1)

  guard.check(force=True)
  vessel.auto_pilot.engage()
  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
  vessel.auto_pilot.target_direction = (0, -1, 0)
  TLM.update("Suborbital landing configured")

def burn_remaining_fuel_for_descent(conn, vessel, guard):
  if not has_usable_thrust(vessel):
    record_mission_event(
      "land_speed_dump_skipped_no_thrust",
      "Land",
      altitude=TLM.read("altitude"),
      apoapsis=TLM.read("apoapsis"),
      periapsis=TLM.read("periapsis"),
      liquid_fuel=TLM.read("liquid_fuel"),
    )
    return

  while (
    TLM.read("altitude") > LANDING_SPEED_DUMP_START_ALTITUDE
    and TLM.read("vertical_speed") < 0
  ):
    guard.check()
    maintain_physics_warp(conn)
    TLM.update("Waiting for speed dump")
    time.sleep(0.1)

  stop_warp(conn)
  TLM.update("Aiming for speed dump")
  aim_landing_retrograde(vessel)
  record_mission_event(
    "land_speed_dump_alignment_start",
    "Land",
    altitude=TLM.read("altitude"),
    apoapsis=TLM.read("apoapsis"),
    periapsis=TLM.read("periapsis"),
    autopilot_error=read_autopilot_error(vessel),
  )

  if not wait_for_autopilot_alignment(
    vessel,
    guard,
    "Aiming for speed dump",
    max_wait=LANDING_SPEED_DUMP_ALIGNMENT_TIMEOUT,
    conn=conn,
    warp_while_waiting=True,
    stable_duration=0.25,
  ):
    record_mission_event(
      "land_speed_dump_alignment_failed",
      "Land",
      altitude=TLM.read("altitude"),
      apoapsis=TLM.read("apoapsis"),
      periapsis=TLM.read("periapsis"),
      autopilot_error=read_autopilot_error(vessel),
    )
    return

  record_mission_event(
    "land_speed_dump_burn_start",
    "Land",
    altitude=TLM.read("altitude"),
    apoapsis=TLM.read("apoapsis"),
    periapsis=TLM.read("periapsis"),
    minimum_apoapsis=LANDING_SPEED_DUMP_MIN_APOAPSIS,
    autopilot_error=read_autopilot_error(vessel),
  )

  vessel.control.throttle = 1.0

  while (
    has_usable_thrust(vessel)
    and TLM.read("apoapsis") > LANDING_SPEED_DUMP_MIN_APOAPSIS
  ):
    guard.check()
    maintain_physics_warp(conn)
    TLM.update("Burning remaining fuel")

    autopilot_error = read_autopilot_error(vessel)
    if autopilot_error is not None and abs(autopilot_error) > AUTOPILOT_ALIGNMENT_ERROR:
      vessel.control.throttle = 0
      record_mission_event(
        "land_speed_dump_alignment_lost",
        "Land",
        altitude=TLM.read("altitude"),
        apoapsis=TLM.read("apoapsis"),
        periapsis=TLM.read("periapsis"),
        autopilot_error=autopilot_error,
      )
      aim_landing_retrograde(vessel)
      if not wait_for_autopilot_alignment(
        vessel,
        guard,
        "Reacquiring speed dump alignment",
        max_wait=10,
        conn=conn,
        warp_while_waiting=True,
        stable_duration=0.25,
      ):
        record_mission_event(
          "land_speed_dump_abandoned_alignment",
          "Land",
          altitude=TLM.read("altitude"),
          apoapsis=TLM.read("apoapsis"),
          periapsis=TLM.read("periapsis"),
          autopilot_error=read_autopilot_error(vessel),
        )
        vessel.control.throttle = 0
        break

    if vessel.control.throttle < 1.0:
      vessel.control.throttle = 1.0

    time.sleep(0.1)

  guard.check(force=True)
  vessel.control.throttle = 0.0
  record_mission_event(
    "land_speed_dump_burn_done",
    "Land",
    altitude=TLM.read("altitude"),
    apoapsis=TLM.read("apoapsis"),
    periapsis=TLM.read("periapsis"),
    minimum_apoapsis=LANDING_SPEED_DUMP_MIN_APOAPSIS,
    usable_thrust_remaining=has_usable_thrust(vessel),
  )

def warp_physics_through_atmosphere(conn, vessel, guard, parachutes_deployed):
  TLM.update("Aerobraking")
  maintain_physics_warp(conn)

  while not vessel_is_down(vessel):
    guard.check()
    maintain_physics_warp(conn)

    if TLM.read("altitude") <= PARACHUTE_DEPLOY_ALTITUDE and not parachutes_deployed:
      TLM.update("Deploying parachutes")
      stop_warp(conn)
      vessel.control.activate_next_stage()
      parachutes_deployed = True

    if parachutes_deployed:
      TLM.update("Descending under parachutes")
    else:
      TLM.update("Aerobraking")

    if (
      TLM.read("altitude") > LANDING_ATMOSPHERE_ALTITUDE and
      TLM.read("vertical_speed") > 0
    ):
      stop_warp(conn)
      return parachutes_deployed

    time.sleep(0.1)

  return parachutes_deployed

def warp_through_aerobraking(conn, vessel, guard):
  engines_dropped = False
  parachutes_deployed = False

  while not vessel_is_down(vessel):
    guard.check()

    if TLM.read("altitude") > LANDING_ATMOSPHERE_ALTITUDE:
      rails_warp_to_atmosphere(conn, "Rails warping to atmosphere", guard)

    if vessel_is_down(vessel):
      break

    TLM.update("Entering atmosphere")
    maintain_physics_warp(conn)

    if not engines_dropped:
      burn_remaining_fuel_for_descent(conn, vessel, guard)
      TLM.update("Dumping engines")
      vessel.control.activate_next_stage()
      engines_dropped = True

    parachutes_deployed = warp_physics_through_atmosphere(
      conn,
      vessel,
      guard,
      parachutes_deployed,
    )

  TLM.update("Landed")
  stop_warp(conn)

def aim_landing_retrograde(vessel):
  vessel.auto_pilot.engage()
  vessel.auto_pilot.reference_frame = vessel.orbital_reference_frame
  vessel.auto_pilot.target_direction = (0, -1, 0)
  vessel.auto_pilot.target_roll = 0

def ensure_vessel_control_available():
  if TLM.read("has_vessel_control"):
    return

  record_mission_event(
    "land_no_vessel_control",
    "Land",
    vessel_control=TLM.read("vessel_control"),
    control_state=TLM.read("control_state"),
    control_source=TLM.read("control_source"),
    control_input_mode=TLM.read("control_input_mode"),
  )
  raise MissionAborted("Land stopped because the vessel no longer has control")

def ensure_deorbit_thrust(vessel, guard):
  ensure_vessel_control_available()

  if has_usable_thrust(vessel) and deorbit_engine_is_active(vessel):
    return

  activate_deorbit_engines(vessel)
  if has_usable_thrust(vessel) and deorbit_engine_is_active(vessel):
    return

  current_stage = vessel.control.current_stage
  next_stage = current_stage - 1
  if stage_has_engine(vessel, next_stage):
    record_mission_event(
      "land_deorbit_stage_for_thrust",
      "Land",
      current_stage=current_stage,
      next_stage=next_stage,
      available_thrust=vessel.available_thrust,
      liquid_fuel=TLM.read("liquid_fuel"),
      control_input_mode=TLM.read("control_input_mode"),
    )
    vessel.control.activate_next_stage()
    time.sleep(0.5)
    guard.check(force=True)
    activate_deorbit_engines(vessel)

  if not has_usable_thrust(vessel) or not deorbit_engine_is_active(vessel):
    record_mission_event(
      "land_deorbit_no_usable_thrust",
      "Land",
      current_stage=vessel.control.current_stage,
      available_thrust=vessel.available_thrust,
      liquid_fuel=TLM.read("liquid_fuel"),
      engine_active=deorbit_engine_is_active(vessel),
      control_input_mode=TLM.read("control_input_mode"),
    )
    raise MissionAborted("Land stopped because no usable deorbit thrust is available")

def deorbit_engine_is_active(vessel):
  return any(
    safe_value(lambda engine=engine: engine.active, False)
    and not engine_uses_resource(engine, "SolidFuel")
    and safe_value(lambda engine=engine: float(engine.available_thrust), 0) > 0.1
    for engine in safe_value(lambda: list(vessel.parts.engines), [])
  )

def activate_deorbit_engines(vessel):
  activated = 0

  for engine in safe_value(lambda: list(vessel.parts.engines), []):
    if engine_uses_resource(engine, "SolidFuel"):
      continue
    if safe_value(lambda engine=engine: float(engine.available_thrust), 0) <= 0.1:
      continue
    if safe_value(lambda engine=engine: engine.active, False):
      continue

    try:
      engine.active = True
      activated += 1
    except Exception:
      pass

  if activated:
    record_mission_event(
      "land_deorbit_engines_activated",
      "Land",
      activated_engines=activated,
    )

def read_actual_thrust(vessel):
  return safe_value(lambda: float(vessel.thrust), 0) or 0

def confirm_deorbit_burn_is_live(vessel, guard, starting_fuel):
  for attempt in range(3):
    time.sleep(0.5)
    guard.check(force=True)

    current_fuel = TLM.read("liquid_fuel")
    actual_thrust = read_actual_thrust(vessel)
    if actual_thrust > 1 or current_fuel < starting_fuel - 0.01:
      return

    record_mission_event(
      "land_deorbit_burn_not_lit",
      "Land",
      attempt=attempt + 1,
      actual_thrust=actual_thrust,
      available_thrust=vessel.available_thrust,
      throttle=vessel.control.throttle,
      liquid_fuel=current_fuel,
      engine_active=deorbit_engine_is_active(vessel),
      control_input_mode=TLM.read("control_input_mode"),
      vessel_control=TLM.read("vessel_control"),
    )
    activate_deorbit_engines(vessel)

    current_stage = vessel.control.current_stage
    next_stage = current_stage - 1
    if stage_has_engine(vessel, next_stage):
      vessel.control.activate_next_stage()
      time.sleep(0.2)
      activate_deorbit_engines(vessel)

  vessel.control.throttle = 0
  raise MissionAborted("Land stopped because the deorbit engine did not produce thrust")

def choose_deorbit_alignment_ut():
  now = TLM.read("ut")
  time_to_apoapsis = TLM.read("time_to_apoapsis")

  apoapsis_arrival_ut = now + time_to_apoapsis
  alignment_ut = max(
    now,
    apoapsis_arrival_ut - LANDING_DEORBIT_ALIGNMENT_BUFFER,
  )
  burn_start_ut = max(
    now,
    apoapsis_arrival_ut - LANDING_DEORBIT_BURN_LEAD_TIME,
  )

  return apoapsis_arrival_ut, alignment_ut, burn_start_ut

def coast_to_deorbit_alignment(conn, guard, alignment_ut):
  try:
    while TLM.read("ut") < alignment_ut:
      guard.check()
      ensure_vessel_control_available()
      TLM.update("Warping to deorbit alignment")
      remaining = alignment_ut - TLM.read("ut")

      if remaining > 3600:
        warp_factor = RAILS_WARP_FACTOR
      elif remaining > 900:
        warp_factor = min(5, RAILS_WARP_FACTOR)
      elif remaining > 240:
        warp_factor = min(4, RAILS_WARP_FACTOR)
      elif remaining > 90:
        warp_factor = min(3, RAILS_WARP_FACTOR)
      elif remaining > 20:
        warp_factor = 1
      else:
        break

      manual_rails_warp_until(
        conn,
        "Warping to deorbit alignment",
        lambda: TLM.read("ut") >= alignment_ut or alignment_ut - TLM.read("ut") <= remaining / 2,
        warp_factor=warp_factor,
        update_interval=0.1,
        guard=guard,
        allow_physics_fallback=False,
      )

    while TLM.read("ut") < alignment_ut:
      guard.check()
      ensure_vessel_control_available()
      TLM.update("Final coast to deorbit alignment")
      time.sleep(0.05)
  finally:
    stop_warp(conn)

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

    configure_suborbital_landing(conn, vessel, guard)
  except Exception as error:
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Suborbital landing")) from error
    raise
  finally:
    close_mission_connection(conn)

def land_rocket():
  record_mission_event("land_enter", "Land")
  conn, vessel = safe_connect("Land")
  if not conn:
    record_mission_event("land_no_connection", "Land")
    raise MissionAborted("Land stopped because no active vessel is available")

  record_mission_event("land_connected", "Land")
  register_mission_connection(conn, vessel, "Land")
  guard = MissionGuard(conn, vessel, "Land")

  try:
    record_mission_event("land_tlm_begin_start", "Land")
    TLM.begin(conn, vessel)
    record_mission_event("land_tlm_begin_done", "Land")
    ensure_vessel_control_available()

    body_name = getattr(vessel.orbit.body, "name", None)
    if body_name != "Kerbin":
      raise MissionAborted(
        f"Land stopped because the vessel is orbiting {body_name or 'unknown'}, not Kerbin"
      )

    TLM.update("Preparing deorbit burn")
    record_mission_event("land_guard_check_start", "Land")
    guard.check(force=True)
    record_mission_event("land_guard_check_done", "Land")

    record_mission_event("land_autopilot_setup_start", "Land")
    aim_landing_retrograde(vessel)
    record_mission_event("land_autopilot_setup_done", "Land")

    apoapsis_arrival_ut, alignment_ut, burn_start_ut = choose_deorbit_alignment_ut()
    record_mission_event(
      "land_warp_to_alignment_start",
      "Land",
      target_ut=apoapsis_arrival_ut,
      alignment_ut=alignment_ut,
      burn_start_ut=burn_start_ut,
      time_to_apoapsis=TLM.read("time_to_apoapsis"),
      orbital_period=TLM.read("orbital_period"),
    )

    coast_to_deorbit_alignment(conn, guard, alignment_ut)

    record_mission_event(
      "land_warp_to_alignment_done",
      "Land",
      time_to_apoapsis=TLM.read("time_to_apoapsis"),
    )
    guard.check(force=True)
    TLM.update("Pointing retrograde")
    aim_landing_retrograde(vessel)
    record_mission_event("land_align_retrograde_start", "Land")
    if not wait_for_autopilot_alignment(
      vessel,
      guard,
      "Pointing retrograde",
      max_wait=45,
      conn=conn,
      warp_while_waiting=True,
    ):
      record_mission_event(
        "land_align_retrograde_failed",
        "Land",
        autopilot_error=read_autopilot_error(vessel),
        time_to_apoapsis=TLM.read("time_to_apoapsis"),
        apoapsis=TLM.read("apoapsis"),
        periapsis=TLM.read("periapsis"),
      )
      raise MissionAborted("Land stopped because retrograde alignment did not settle")

    record_mission_event(
      "land_align_retrograde_done",
      "Land",
      autopilot_error=read_autopilot_error(vessel),
    )

    try:
      while TLM.read("ut") < burn_start_ut:
        guard.check()
        TLM.update("Waiting for deorbit burn")
        autopilot_error = read_autopilot_error(vessel)
        if autopilot_error is not None and abs(autopilot_error) > LANDING_DEORBIT_DRIFT_ERROR:
          record_mission_event(
            "land_align_retrograde_drifted_before_burn",
            "Land",
            autopilot_error=autopilot_error,
            time_to_apoapsis=TLM.read("time_to_apoapsis"),
          )
          aim_landing_retrograde(vessel)
          if not wait_for_autopilot_alignment(
            vessel,
            guard,
            "Reacquiring retrograde",
            max_wait=10,
            conn=conn,
            warp_while_waiting=True,
          ):
            raise MissionAborted("Land stopped because retrograde alignment was lost before deorbit burn")

        manual_physics_warp_until(
          conn,
          "Waiting for deorbit burn",
          lambda: TLM.read("ut") >= burn_start_ut,
          warp_factor=3,
          guard=guard,
        )
    finally:
      stop_warp(conn)

    aim_landing_retrograde(vessel)
    if not wait_for_autopilot_alignment(
      vessel,
      guard,
      "Final deorbit alignment",
      max_wait=12,
      conn=conn,
      warp_while_waiting=True,
    ):
      record_mission_event(
        "land_final_align_retrograde_failed",
        "Land",
        autopilot_error=read_autopilot_error(vessel),
        time_to_apoapsis=TLM.read("time_to_apoapsis"),
        apoapsis=TLM.read("apoapsis"),
        periapsis=TLM.read("periapsis"),
      )
      raise MissionAborted("Land stopped because retrograde alignment was not ready at deorbit burn")

    record_mission_event(
      "land_final_align_retrograde_done",
      "Land",
      autopilot_error=read_autopilot_error(vessel),
      time_to_apoapsis=TLM.read("time_to_apoapsis"),
      apoapsis=TLM.read("apoapsis"),
      periapsis=TLM.read("periapsis"),
    )

    ensure_deorbit_thrust(vessel, guard)
    ensure_vessel_control_available()
    TLM.update("Lowering periapsis")
    starting_fuel = TLM.read("liquid_fuel")
    vessel.control.throttle = LANDING_DEORBIT_THROTTLE
    confirm_deorbit_burn_is_live(vessel, guard, starting_fuel)
    record_mission_event(
      "land_deorbit_burn_start",
      "Land",
      autopilot_error=read_autopilot_error(vessel),
      time_to_apoapsis=TLM.read("time_to_apoapsis"),
      apoapsis=TLM.read("apoapsis"),
      periapsis=TLM.read("periapsis"),
      available_thrust=vessel.available_thrust,
      actual_thrust=read_actual_thrust(vessel),
      liquid_fuel=TLM.read("liquid_fuel"),
      throttle=LANDING_DEORBIT_THROTTLE,
    )
    burn_started_at = time.monotonic()
    last_progress_at = burn_started_at
    best_periapsis = TLM.read("periapsis")
    last_progress_report = burn_started_at

    while TLM.read("periapsis") > LANDING_DEORBIT_PERIAPSIS:
      guard.check()
      TLM.update("Lowering periapsis")
      current_periapsis = TLM.read("periapsis")

      if current_periapsis < best_periapsis - LANDING_DEORBIT_PROGRESS_MIN_DROP:
        best_periapsis = current_periapsis
        last_progress_at = time.monotonic()

      if time.monotonic() - last_progress_report >= 5:
        record_mission_event(
          "land_deorbit_burn_progress",
          "Land",
          apoapsis=TLM.read("apoapsis"),
          periapsis=current_periapsis,
          best_periapsis=best_periapsis,
          target_periapsis=LANDING_DEORBIT_PERIAPSIS,
          available_thrust=vessel.available_thrust,
          actual_thrust=read_actual_thrust(vessel),
          liquid_fuel=TLM.read("liquid_fuel"),
          throttle=vessel.control.throttle,
          elapsed_seconds=time.monotonic() - burn_started_at,
        )
        last_progress_report = time.monotonic()

      if time.monotonic() - last_progress_at > LANDING_DEORBIT_PROGRESS_TIMEOUT:
        vessel.control.throttle = 0
        record_mission_event(
          "land_deorbit_burn_no_progress",
          "Land",
          apoapsis=TLM.read("apoapsis"),
          periapsis=current_periapsis,
          best_periapsis=best_periapsis,
          available_thrust=vessel.available_thrust,
          actual_thrust=read_actual_thrust(vessel),
          liquid_fuel=TLM.read("liquid_fuel"),
          throttle=LANDING_DEORBIT_THROTTLE,
          elapsed_seconds=time.monotonic() - burn_started_at,
        )
        raise MissionAborted("Land stopped because deorbit burn did not lower periapsis")

      autopilot_error = read_autopilot_error(vessel)
      if autopilot_error is not None and abs(autopilot_error) > AUTOPILOT_ALIGNMENT_ERROR:
        vessel.control.throttle = 0
        record_mission_event(
          "land_align_retrograde_lost",
          "Land",
          autopilot_error=autopilot_error,
          apoapsis=TLM.read("apoapsis"),
          periapsis=TLM.read("periapsis"),
        )

        aim_landing_retrograde(vessel)
        if not wait_for_autopilot_alignment(
          vessel,
          guard,
          "Reacquiring retrograde",
          max_wait=10,
          conn=conn,
          warp_while_waiting=True,
        ):
          if TLM.read("periapsis") <= LANDING_ATMOSPHERE_ALTITUDE:
            record_mission_event(
              "land_deorbit_alignment_abandoned_suborbital",
              "Land",
              autopilot_error=read_autopilot_error(vessel),
              apoapsis=TLM.read("apoapsis"),
              periapsis=TLM.read("periapsis"),
            )
            break

          raise MissionAborted("Land stopped because retrograde alignment was lost")

        vessel.control.throttle = LANDING_DEORBIT_THROTTLE

      if not has_usable_thrust(vessel):
        if TLM.read("periapsis") <= LANDING_ATMOSPHERE_ALTITUDE:
          break

        raise MissionAborted("Land stopped because deorbit burn ran out of fuel")

      if vessel.control.throttle < LANDING_DEORBIT_THROTTLE:
        vessel.control.throttle = LANDING_DEORBIT_THROTTLE

      time.sleep(0.1)

    guard.check(force=True)
    vessel.control.throttle = 0.0
    record_mission_event("land_deorbit_burn_done", "Land", periapsis=TLM.read("periapsis"))

    warp_through_aerobraking(conn, vessel, guard)
  except Exception as error:
    record_mission_event("land_error", "Land", error=str(error))
    if is_vessel_lost_error(error):
      raise MissionAborted(mission_aborted_message("Land")) from error
    raise
  finally:
    record_mission_event("land_close", "Land")
    close_mission_connection(conn)

