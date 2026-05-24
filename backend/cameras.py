import os

from config import load_env_file
from krpc_utils import safe_value

load_env_file()

CAMERA_MODULE_PATTERNS = (
  "camera",
  "hullcam",
  "mumechmodulehullcamera",
  "externalcameraselector",
)

CAMERA_STREAM_URL = os.environ.get("KSP_CAMERA_STREAM_URL", "")
CAMERA_STREAM_KIND = os.environ.get("KSP_CAMERA_STREAM_KIND", "image")


def normalize_stream_url(url):
  if not url:
    return None

  if url.startswith(("http://", "https://")):
    return url

  return f"http://{url}"


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


def get_camera_snapshot(vessel):
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
    module_names = [
      safe_value(lambda module=module: module.name, "")
      for module in camera_modules
    ]

    cameras.append({
      "id": f"{index}:{part_name}",
      "index": len(cameras),
      "part_name": part_name,
      "label": get_part_label(part),
      "modules": module_names,
    })

  selected_camera = cameras[0] if cameras else None

  if selected_camera:
    selected_camera = {
      **selected_camera,
      "stream_url": get_camera_stream_url(selected_camera),
      "stream_kind": CAMERA_STREAM_KIND,
    }

  return {
    "available": len(cameras) > 0,
    "count": len(cameras),
    "selected_index": 0 if cameras else None,
    "selected": selected_camera,
    "cameras": cameras,
  }
