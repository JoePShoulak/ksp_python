import time

from krpc_utils import stop_warp
from mission_state import record_mission_event
from telemetry import TLM

from .constants import (
  AUTOPILOT_ALIGNMENT_ERROR,
  AUTOPILOT_ALIGNMENT_TIMEOUT,
  CIRCULARIZATION_ATMOSPHERE_ALTITUDE,
  DESCENT_PHYSICS_WARP_FACTOR,
  LANDING_ATMOSPHERE_ALTITUDE,
  RAILS_WARP_FACTOR,
)

def get_current_warp_factor(conn):
  return max(
    conn.space_center.rails_warp_factor,
    conn.space_center.physics_warp_factor,
  )

def set_physics_warp(conn, warp_factor):
  try:
    if conn.space_center.rails_warp_factor > 0:
      conn.space_center.rails_warp_factor = 0

    if conn.space_center.physics_warp_factor != warp_factor:
      conn.space_center.physics_warp_factor = warp_factor
  except Exception:
    pass

def set_rails_warp(conn, warp_factor):
  try:
    if conn.space_center.physics_warp_factor > 0:
      conn.space_center.physics_warp_factor = 0

    if conn.space_center.rails_warp_factor != warp_factor:
      conn.space_center.rails_warp_factor = warp_factor
  except Exception:
    pass

def maintain_coast_warp(
  conn,
  altitude=None,
  physics_warp_factor=DESCENT_PHYSICS_WARP_FACTOR,
  allow_rails=True,
):
  if altitude is None:
    altitude = TLM.read("altitude")

  if altitude < CIRCULARIZATION_ATMOSPHERE_ALTITUDE or not allow_rails:
    set_physics_warp(conn, physics_warp_factor)
  else:
    set_rails_warp(conn, min(RAILS_WARP_FACTOR, conn.space_center.maximum_rails_warp_factor))

def wait_for_autopilot_alignment(
  vessel,
  guard,
  status,
  max_wait=AUTOPILOT_ALIGNMENT_TIMEOUT,
  conn=None,
  warp_while_waiting=False,
  physics_warp_factor=DESCENT_PHYSICS_WARP_FACTOR,
  warp_max_error=None,
  stable_duration=0.5,
  min_wait=0.25,
):
  started_at = time.monotonic()
  stable_since = None

  try:
    while time.monotonic() - started_at < max_wait:
      now = time.monotonic()
      guard.check()
      TLM.update(status)

      try:
        autopilot_error = abs(vessel.auto_pilot.error)

        if autopilot_error <= AUTOPILOT_ALIGNMENT_ERROR:
          if stable_since is None:
            stable_since = now

          if (
            now - started_at >= min_wait
            and now - stable_since >= stable_duration
          ):
            return True
        else:
          stable_since = None
      except Exception:
        return False

      if conn and warp_while_waiting:
        if warp_max_error is not None and autopilot_error > warp_max_error:
          stop_warp(conn)
        else:
          maintain_coast_warp(
            conn,
            physics_warp_factor=physics_warp_factor,
            allow_rails=False,
          )

      time.sleep(0.1)

    return False
  finally:
    if conn and warp_while_waiting:
      stop_warp(conn)

def read_autopilot_error(vessel):
  try:
    return vessel.auto_pilot.error
  except Exception:
    return None

def reset_manual_controls(vessel):
  vessel.control.abort = False
  vessel.control.throttle = 0
  vessel.control.pitch = 0
  vessel.control.yaw = 0
  vessel.control.roll = 0
  vessel.control.forward = 0
  vessel.control.right = 0
  vessel.control.up = 0

def manual_physics_warp_until(
  conn,
  status,
  stop_condition,
  warp_factor=DESCENT_PHYSICS_WARP_FACTOR,
  update_interval=0.1,
  abort_condition=None,
  guard=None,
):
  if abort_condition is None:
    abort_condition = lambda: False

  try:
    while not stop_condition() and not abort_condition():
      if guard:
        guard.check()

      TLM.update(status)

      set_physics_warp(conn, warp_factor)

      time.sleep(update_interval)

  finally:
    stop_warp(conn)

def maintain_physics_warp(conn, warp_factor=DESCENT_PHYSICS_WARP_FACTOR):
  if warp_factor <= 0:
    return

  set_physics_warp(conn, warp_factor)

def manual_rails_warp_until(
  conn,
  status,
  stop_condition,
  warp_factor=5,
  update_interval=0.1,
  abort_condition=None,
  guard=None,
  allow_physics_fallback=False,
  physics_fallback_after=1.0,
):
  fallback_pending_since = None
  use_physics_fallback = False
  fallback_reported = False
  last_slow_warp_report = 0

  if abort_condition is None:
    abort_condition = lambda: False

  try:
    while not stop_condition() and not abort_condition():
      if guard:
        guard.check()

      TLM.update(status)

      if use_physics_fallback:
        set_physics_warp(conn, DESCENT_PHYSICS_WARP_FACTOR)
      else:
        max_warp = conn.space_center.maximum_rails_warp_factor
        selected_warp = min(warp_factor, max_warp)
        set_rails_warp(conn, selected_warp)
        current_warp = get_current_warp_factor(conn)

        if (
          selected_warp < warp_factor
          or current_warp < selected_warp
        ):
          now = time.monotonic()
          if now - last_slow_warp_report >= 15:
            record_mission_event(
              "rails_warp_rate_limited",
              None,
              status=status,
              target_warp=warp_factor,
              selected_warp=selected_warp,
              current_warp=current_warp,
              maximum_rails_warp=max_warp,
            )
            last_slow_warp_report = now

        if allow_physics_fallback and current_warp <= 1:
          if fallback_pending_since is None:
            fallback_pending_since = time.monotonic()
          elif time.monotonic() - fallback_pending_since >= physics_fallback_after:
            use_physics_fallback = True
            if not fallback_reported:
              record_mission_event(
                "rails_warp_fallback_to_physics",
                None,
                status=status,
                target_warp=selected_warp,
              )
              fallback_reported = True
            set_physics_warp(conn, DESCENT_PHYSICS_WARP_FACTOR)
        else:
          fallback_pending_since = None

      time.sleep(update_interval)

  finally:
    stop_warp(conn)

def coast_to_ut(conn, status, target_ut, warp_factor=RAILS_WARP_FACTOR, guard=None):
  target_ut = max(target_ut, TLM.read("ut"))

  if target_ut <= TLM.read("ut") + 0.5:
    return

  manual_rails_warp_until(
    conn,
    status,
    lambda: TLM.read("ut") >= target_ut,
    warp_factor=warp_factor,
    guard=guard,
    allow_physics_fallback=True,
  )

def rails_coast_to_ut(conn, status, target_ut, warp_factor=RAILS_WARP_FACTOR, guard=None):
  target_ut = max(target_ut, TLM.read("ut"))

  if target_ut <= TLM.read("ut") + 0.5:
    return

  manual_rails_warp_until(
    conn,
    status,
    lambda: TLM.read("ut") >= target_ut,
    warp_factor=warp_factor,
    guard=guard,
    allow_physics_fallback=False,
  )

def warp_to_ut(conn, status, target_ut, warp_factor=RAILS_WARP_FACTOR, guard=None):
  if guard:
    guard.check(force=True)

  selected_warp = min(warp_factor, conn.space_center.maximum_rails_warp_factor)
  target_ut = max(target_ut, TLM.read("ut"))

  if target_ut <= TLM.read("ut") + 0.5:
    return

  TLM.update(status)

  try:
    try:
      conn.space_center.warp_to(
        target_ut,
        max_rails_warp_factor=selected_warp,
        max_physics_warp_factor=0,
      )
    except TypeError:
      conn.space_center.warp_to(target_ut, selected_warp, 0)
  finally:
    stop_warp(conn)

  if guard:
    guard.check(force=True)

  TLM.update(status)

def rails_warp_toward_periapsis(conn, status, guard, lead_time=45):
  while TLM.read("time_to_periapsis") > lead_time:
    guard.check()
    coast_time = min(TLM.read("time_to_periapsis") - lead_time, 300)
    target_ut = TLM.read("ut") + max(1, coast_time)
    coast_to_ut(conn, status, target_ut, guard=guard)

def rails_warp_to_atmosphere(conn, status, guard, update_interval=0.1):
  try:
    while TLM.read("altitude") > LANDING_ATMOSPHERE_ALTITUDE:
      guard.check()
      TLM.update(status)
      set_rails_warp(conn, RAILS_WARP_FACTOR)
      time.sleep(update_interval)
  finally:
    stop_warp(conn)

