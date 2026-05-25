import os

import krpc # type: ignore

from config import load_env_file


load_env_file()


def get_krpc_connection_config():
  return {
    "address": os.environ.get("KRPC_ADDRESS", "192.168.20.104"),
    "rpc_port": int(os.environ.get("KRPC_RPC_PORT", "50000")),
    "stream_port": int(os.environ.get("KRPC_STREAM_PORT", "50001")),
  }


def safe_value(getter, fallback=None):
  try:
    return getter()
  except Exception:
    return fallback


def get_scene_name(conn):
  try:
    current_scene = conn.space_center.current_game_scene
  except Exception:
    return "unknown"

  return str(current_scene)


def get_vessel_identifier(vessel):
  try:
    return vessel.name
  except Exception:
    pass

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


def safe_connect(name):
  try:
    conn = krpc.connect(name=name, **get_krpc_connection_config())
  except Exception:
    return False, False

  try:
    vessel = conn.space_center.active_vessel
  except Exception:
    conn.close()
    return False, False

  if not vessel:
    conn.close()
    return False, False

  if not vessel_is_readable(vessel):
    conn.close()
    return False, False

  return conn, vessel
