import json
import os
import shutil
import threading
import time


LOG_DIR = os.path.join(os.path.dirname(__file__), ".runtime", "telemetry_logs")
CURRENT_LOG_PATH = os.path.join(LOG_DIR, "current_flight.jsonl")
LAST_LOG_PATH = os.path.join(LOG_DIR, "last_flight.jsonl")
LAST_SUMMARY_PATH = os.path.join(LOG_DIR, "last_flight_summary.json")
MIN_SAMPLE_INTERVAL_SECONDS = 0.25

_LOCK = threading.Lock()
_ACTIVE = None


def start_flight(action):
  global _ACTIVE

  os.makedirs(LOG_DIR, exist_ok=True)

  with _LOCK:
    _ACTIVE = {
      "action": action,
      "started_at": time.time(),
      "last_sample_at": 0,
      "last_status": None,
      "sample_count": 0,
    }

    with open(CURRENT_LOG_PATH, "w", encoding="utf-8") as log_file:
      log_file.write("")


def finish_flight(error=None):
  global _ACTIVE

  with _LOCK:
    active = _ACTIVE
    _ACTIVE = None

  if not active:
    return

  finished_at = time.time()
  summary = {
    "action": active["action"],
    "started_at": active["started_at"],
    "finished_at": finished_at,
    "duration_seconds": finished_at - active["started_at"],
    "sample_count": active["sample_count"],
    "error": error,
  }

  os.makedirs(LOG_DIR, exist_ok=True)

  if os.path.exists(CURRENT_LOG_PATH):
    shutil.copyfile(CURRENT_LOG_PATH, LAST_LOG_PATH)
  else:
    with open(LAST_LOG_PATH, "w", encoding="utf-8") as log_file:
      log_file.write("")

  with open(LAST_SUMMARY_PATH, "w", encoding="utf-8") as summary_file:
    json.dump(summary, summary_file, indent=2, sort_keys=True)


def record_snapshot(snapshot):
  if not snapshot:
    return

  now = time.time()

  with _LOCK:
    if not _ACTIVE:
      return

    status = snapshot.get("status")
    should_record = (
      now - _ACTIVE["last_sample_at"] >= MIN_SAMPLE_INTERVAL_SECONDS
      or status != _ACTIVE["last_status"]
    )

    if not should_record:
      return

    _ACTIVE["last_sample_at"] = now
    _ACTIVE["last_status"] = status
    _ACTIVE["sample_count"] += 1
    action = _ACTIVE["action"]
    started_at = _ACTIVE["started_at"]
    sample_index = _ACTIVE["sample_count"]

  entry = {
    "sample": sample_index,
    "recorded_at": now,
    "elapsed_seconds": now - started_at,
    "action": action,
    "telemetry": make_json_safe(snapshot),
  }

  try:
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(CURRENT_LOG_PATH, "a", encoding="utf-8") as log_file:
      log_file.write(json.dumps(entry, sort_keys=True) + "\n")
  except Exception as error:
    print(f"[flight-recorder] failed to write telemetry sample: {error}", flush=True)


def read_last_flight(limit=None):
  summary = None
  entries = []

  if os.path.exists(LAST_SUMMARY_PATH):
    with open(LAST_SUMMARY_PATH, "r", encoding="utf-8") as summary_file:
      summary = json.load(summary_file)

  if os.path.exists(LAST_LOG_PATH):
    with open(LAST_LOG_PATH, "r", encoding="utf-8") as log_file:
      lines = log_file.readlines()

    if limit and limit > 0:
      lines = lines[-limit:]

    for line in lines:
      line = line.strip()

      if line:
        entries.append(json.loads(line))

  return {
    "summary": summary,
    "entries": entries,
    "entry_count": len(entries),
    "available": bool(summary or entries),
  }


def make_json_safe(value):
  if value is None or isinstance(value, (bool, int, float, str)):
    return value

  if isinstance(value, dict):
    return {
      str(key): make_json_safe(item)
      for key, item in value.items()
    }

  if isinstance(value, (list, tuple)):
    return [make_json_safe(item) for item in value]

  return str(value)
