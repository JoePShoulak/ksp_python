import os
import json
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

from config import load_env_file

load_env_file()

CAMERA_MODULE_PATTERNS = (
  "camera",
  "hullcam",
  "mumechmodulehullcamera",
  "externalcameraselector",
)

DEFAULT_CAMERA_STREAM_URL = f"http://{os.environ.get('KRPC_ADDRESS', '192.168.20.104')}:8080/"
CAMERA_STREAM_URL = os.environ.get("KSP_CAMERA_STREAM_URL") or DEFAULT_CAMERA_STREAM_URL
CAMERA_STREAM_KIND = os.environ.get("KSP_CAMERA_STREAM_KIND", "image")
CAMERA_DISCOVERY_TIMEOUT = float(os.environ.get("KSP_CAMERA_DISCOVERY_TIMEOUT", "1.5"))
CAMERA_PUBLIC_PATH_PREFIX = os.environ.get("KSP_CAMERA_PUBLIC_PATH_PREFIX", "/jrti")


def safe_value(getter, fallback=None):
  try:
    return getter()
  except Exception:
    return fallback


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


def get_jrti_base_url():
  return normalize_stream_url(CAMERA_STREAM_URL)


def get_jrti_camera_url(path):
  base_url = get_jrti_base_url()

  if not base_url:
    return None

  return urljoin(base_url, path)


def get_public_jrti_url(path):
  if not path:
    return None

  if path.startswith(("http://", "https://")):
    return path

  prefix = CAMERA_PUBLIC_PATH_PREFIX.rstrip("/")

  if not prefix:
    return path

  return f"{prefix}/{path.lstrip('/')}"


def get_public_stream_url(url):
  parsed_url = urlparse(url or "")
  parsed_base = urlparse(get_jrti_base_url() or "")

  if (
    CAMERA_PUBLIC_PATH_PREFIX
    and parsed_url.scheme
    and parsed_url.netloc == parsed_base.netloc
  ):
    path = parsed_url.path or "/"
    if parsed_url.query:
      path = f"{path}?{parsed_url.query}"

    return get_public_jrti_url(path)

  return url


def read_jrti_cameras():
  cameras_url = get_jrti_camera_url("/cameras")

  if not cameras_url:
    return []

  try:
    with urlopen(cameras_url, timeout=CAMERA_DISCOVERY_TIMEOUT) as response:
      data = json.loads(response.read().decode("utf-8"))
  except Exception:
    return []

  if isinstance(data, dict):
    cameras = data.get("value", [])
  else:
    cameras = data

  if not isinstance(cameras, list):
    return []

  return [
    camera
    for camera in cameras
    if isinstance(camera, dict)
  ]


def normalize_jrti_camera(camera, index):
  stream_path = camera.get("streamUrl") or f"/viewer.html?id={camera.get('id')}"
  snapshot_path = camera.get("snapshotUrl")

  return {
    "id": str(camera.get("id", f"jrti-{index}")),
    "index": index,
    "part_name": str(camera.get("id", f"jrti-{index}")),
    "label": camera.get("name") or f"JRTI Camera {index + 1}",
    "modules": [],
    "source": "jrti",
    "streaming": bool(camera.get("streaming")),
    "viewer_count": camera.get("viewerCount"),
    "snapshot_url": get_public_jrti_url(snapshot_path) if snapshot_path else None,
    "stream_url": get_public_jrti_url(stream_path),
    "stream_kind": "iframe",
  }


def get_jrti_camera_snapshot():
  jrti_cameras = [
    normalize_jrti_camera(camera, index)
    for index, camera in enumerate(read_jrti_cameras())
  ]

  if not jrti_cameras:
    return None

  selected_camera = {
    "id": "jrti-dashboard",
    "index": None,
    "part_name": "jrti-dashboard",
    "label": "JRTI Dashboard",
    "modules": [],
    "source": "jrti_dashboard",
    "streaming": any(camera["streaming"] for camera in jrti_cameras),
    "stream_url": get_public_jrti_url("/"),
    "stream_kind": "iframe",
  }

  return {
    "available": True,
    "count": len(jrti_cameras),
    "selected_index": None,
    "selected": selected_camera,
    "stream_configured": bool(CAMERA_STREAM_URL),
    "source": "jrti",
    "cameras": jrti_cameras,
  }


def get_configured_stream_camera():
  if not CAMERA_STREAM_URL:
    return None

  camera = {
    "id": "jrti-stream",
    "index": 0,
    "part_name": "jrti-stream",
    "label": "JRTI Stream",
    "modules": [],
    "source": "configured_stream",
  }

  return {
    **camera,
    "stream_url": get_public_stream_url(get_camera_stream_url(camera)),
    "stream_kind": CAMERA_STREAM_KIND,
  }


def get_camera_snapshot(vessel):
  jrti_snapshot = get_jrti_camera_snapshot()

  if jrti_snapshot:
    return jrti_snapshot

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
      "stream_url": get_public_stream_url(get_camera_stream_url(selected_camera)),
      "stream_kind": CAMERA_STREAM_KIND,
    }
  else:
    selected_camera = get_configured_stream_camera()

  return {
    "available": bool(cameras or selected_camera),
    "count": len(cameras),
    "selected_index": 0 if cameras else None,
    "selected": selected_camera,
    "stream_configured": bool(CAMERA_STREAM_URL),
    "cameras": cameras,
  }
