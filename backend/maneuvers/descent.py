import time

from krpc_utils import safe_connect, stop_warp
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
  LANDING_DEORBIT_THROTTLE,
  PARACHUTE_DEPLOY_ALTITUDE,
  RAILS_WARP_FACTOR,
)
from .control import (
  coast_to_ut,
  maintain_coast_warp,
  maintain_physics_warp,
  rails_warp_to_atmosphere,
  read_autopilot_error,
  wait_for_autopilot_alignment,
)
from .vessel import has_usable_thrust, vessel_is_down

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
    return

  TLM.update("Burning remaining fuel")
  vessel.auto_pilot.target_direction = (0, -1, 0)
  vessel.control.throttle = 1.0

  while has_usable_thrust(vessel):
    guard.check()
    maintain_physics_warp(conn)
    TLM.update("Burning remaining fuel")

    if vessel.control.throttle < 1.0:
      vessel.control.throttle = 1.0

    time.sleep(0.1)

  guard.check(force=True)
  vessel.control.throttle = 0.0

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
    TLM.update("Preparing deorbit burn")
    record_mission_event("land_guard_check_start", "Land")
    guard.check(force=True)
    record_mission_event("land_guard_check_done", "Land")

    record_mission_event("land_autopilot_setup_start", "Land")
    aim_landing_retrograde(vessel)
    record_mission_event("land_autopilot_setup_done", "Land")

    apoapsis_arrival_ut = TLM.read("ut") + TLM.read("time_to_apoapsis")
    alignment_ut = max(
      TLM.read("ut"),
      apoapsis_arrival_ut - LANDING_DEORBIT_ALIGNMENT_BUFFER,
    )
    burn_start_ut = max(
      TLM.read("ut"),
      apoapsis_arrival_ut - LANDING_DEORBIT_BURN_LEAD_TIME,
    )
    record_mission_event(
      "land_warp_to_alignment_start",
      "Land",
      target_ut=apoapsis_arrival_ut,
      alignment_ut=alignment_ut,
      burn_start_ut=burn_start_ut,
      time_to_apoapsis=TLM.read("time_to_apoapsis"),
    )

    coast_to_ut(
      conn,
      "Warping to deorbit alignment",
      alignment_ut,
      warp_factor=RAILS_WARP_FACTOR,
      guard=guard,
    )

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

        maintain_coast_warp(conn)
        time.sleep(0.05)
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

    TLM.update("Lowering periapsis")
    vessel.control.throttle = LANDING_DEORBIT_THROTTLE
    record_mission_event(
      "land_deorbit_burn_start",
      "Land",
      autopilot_error=read_autopilot_error(vessel),
      time_to_apoapsis=TLM.read("time_to_apoapsis"),
      apoapsis=TLM.read("apoapsis"),
      periapsis=TLM.read("periapsis"),
    )

    while TLM.read("periapsis") > LANDING_DEORBIT_PERIAPSIS:
      guard.check()
      TLM.update("Lowering periapsis")

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
          raise MissionAborted("Land stopped because retrograde alignment was lost")

        vessel.control.throttle = LANDING_DEORBIT_THROTTLE

      if not has_usable_thrust(vessel):
        if TLM.read("periapsis") <= LANDING_ATMOSPHERE_ALTITUDE:
          break

        raise MissionAborted("Land stopped because deorbit burn ran out of fuel")

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

