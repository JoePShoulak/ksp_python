import os
import threading
import time

import krpc # type: ignore

from config import load_env_file


load_env_file()

KRPC_CONNECTION_LOCK = threading.Lock()
KRPC_CONNECTION_SEQUENCE = 0
KRPC_CONNECTIONS = {}
KRPC_CONNECTION_EVENTS = []
KRPC_CONNECTION_EVENT_LIMIT = 120


def get_krpc_connection_config():
  return {
    "address": os.environ.get("KRPC_ADDRESS", "192.168.20.104"),
    "rpc_port": int(os.environ.get("KRPC_RPC_PORT", "50000")),
    "stream_port": int(os.environ.get("KRPC_STREAM_PORT", "50001")),
  }


def record_connection_event(event, name=None, connection_id=None, **details):
  entry = {
    "time": round(time.time(), 3),
    "event": event,
    "name": name,
    "connection_id": connection_id,
    "details": details,
  }

  with KRPC_CONNECTION_LOCK:
    KRPC_CONNECTION_EVENTS.append(entry)
    del KRPC_CONNECTION_EVENTS[:-KRPC_CONNECTION_EVENT_LIMIT]

  detail_text = f" {details}" if details else ""
  print(
    f"[krpc] {event} name={name or '-'} id={connection_id or '-'}{detail_text}",
    flush=True,
  )


def remember_connection(conn, name):
  global KRPC_CONNECTION_SEQUENCE

  with KRPC_CONNECTION_LOCK:
    KRPC_CONNECTION_SEQUENCE += 1
    connection_id = KRPC_CONNECTION_SEQUENCE
    KRPC_CONNECTIONS[id(conn)] = {
      "id": connection_id,
      "name": name,
      "opened_at": time.time(),
      "closed_at": None,
      "stream_count": 0,
      "close_reason": None,
    }

  record_connection_event("open", name, connection_id)
  return connection_id


def mark_connection_streams(conn, stream_count):
  if not conn:
    return

  with KRPC_CONNECTION_LOCK:
    entry = KRPC_CONNECTIONS.get(id(conn))

    if entry:
      entry["stream_count"] = stream_count
      connection_id = entry["id"]
      name = entry["name"]
    else:
      connection_id = None
      name = None

  record_connection_event("streams_attached", name, connection_id, stream_count=stream_count)


def forget_connection(conn, reason="closed"):
  if not conn:
    return

  with KRPC_CONNECTION_LOCK:
    entry = KRPC_CONNECTIONS.get(id(conn))

    if not entry:
      return

    if entry["closed_at"] is not None:
      return

    entry["closed_at"] = time.time()
    entry["close_reason"] = reason
    connection_id = entry["id"]
    name = entry["name"]

  record_connection_event("close", name, connection_id, reason=reason)


def get_connection_ledger():
  now = time.time()

  with KRPC_CONNECTION_LOCK:
    connections = [
      {
        **entry,
        "age_seconds": now - entry["opened_at"],
        "open": entry["closed_at"] is None,
      }
      for entry in KRPC_CONNECTIONS.values()
    ]
    events = list(KRPC_CONNECTION_EVENTS)

  connections.sort(key=lambda entry: entry["id"], reverse=True)

  return {
    "open_count": sum(1 for entry in connections if entry["open"]),
    "connections": connections[:30],
    "events": events[-30:],
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
      forget_connection(conn)
    except Exception:
      forget_connection(conn, reason="close_error")
      pass


def safe_connect(name, attempts=3, retry_delay=0.15):
  for attempt in range(attempts):
    try:
      conn = krpc.connect(name=name, **get_krpc_connection_config())
      remember_connection(conn, name)
    except Exception:
      conn = None
      record_connection_event("connect_failed", name, attempt=attempt + 1)

    if conn:
      try:
        vessel = conn.space_center.active_vessel

        if vessel and vessel_is_readable(vessel):
          record_connection_event(
            "active_vessel_ready",
            name,
            KRPC_CONNECTIONS.get(id(conn), {}).get("id"),
            vessel_name=safe_value(lambda: vessel.name),
          )
          return conn, vessel
      except Exception:
        pass

      record_connection_event(
        "active_vessel_unreadable",
        name,
        KRPC_CONNECTIONS.get(id(conn), {}).get("id"),
      )
      close_connection(conn, stop_warp_first=False)

    if attempt < attempts - 1:
      time.sleep(retry_delay)

  return False, False
