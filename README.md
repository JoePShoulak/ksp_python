# KSP Control Panel

KSP Control Panel is a LAN-hosted mission dashboard and automation layer for
Kerbal Space Program. It combines a Flask backend, a React/Vite frontend, kRPC
vessel control, live telemetry, p5 visualizations, optional JRTI/Hullcam camera
feeds, and a package-based Ubuntu deployment flow.

The project is intentionally built around one active KSP control lane. Mission
actions, telemetry reads, abort/release handling, and kRPC connection ownership
are coordinated in the backend so the UI can stay responsive without issuing
conflicting vessel commands.

## What It Does

- Displays live vessel status, numerical telemetry, ascent plots, Kerbin-system
  position data, resources, communications, time warp state, and camera feeds.
- Runs mission actions through the backend, including launch, wait, landing,
  Mun flyby, circularization, and an LKO tourism sequence.
- Keeps a telemetry cache warm while idle so the dashboard can render without
  repeatedly opening expensive kRPC connections.
- Guards active missions against vessel loss, active-vessel changes, MET
  rollback after revert, stale kRPC connections, and explicit abort requests.
- Records the last action flight log under backend runtime storage and exposes
  it through the API.
- Deploys to the HP1 Ubuntu host with a tar package, systemd backend service,
  and Nginx frontend/API proxy.

## System Shape

```text
Browser
  -> React/Vite dashboard
  -> /api requests
  -> Flask backend
  -> kRPC RPC/stream ports
  -> Kerbal Space Program active vessel

Optional camera path:
Browser
  -> /jrti, /camera, /viewer.html, etc.
  -> JRTI/Hullcam stream host
```

Production currently uses:

```text
Browser
  -> http://192.168.20.21:5173
  -> Nginx static frontend
  -> /api proxied to 127.0.0.1:5000
  -> Flask backend
  -> kRPC at 192.168.20.104:50000/50001
```

## Repository Layout

| Path | Purpose |
| --- | --- |
| `backend/` | Flask API, kRPC connection handling, telemetry cache, mission guards, flight recorder, camera discovery |
| `backend/maneuvers/` | Vessel control routines for ascent, circularization, descent, transfer, mission sequences, and low-level control |
| `frontend/` | React dashboard, action controls, telemetry panels, popout views, p5 visualizations, Vite proxy config |
| `deploy/` | Developer-side package/deploy wrappers and target-side apply scripts |
| `deploy/ubuntu/` | Ubuntu bootstrap, systemd unit, Nginx config, production deploy script, environment example |
| `docs/deployment.md` | Focused production deployment reference |

## Backend

The backend entrypoint is `backend/main.py`. It runs Flask directly on
`0.0.0.0` and defaults to port `5000`.

Important backend modules:

| Module | Role |
| --- | --- |
| `main.py` | API routes, action thread lifecycle, telemetry stream startup, release/revert commands |
| `krpc_utils.py` | kRPC config, connection retry/open/close helpers, connection ledger, safe value reads |
| `telemetry.py` | Fast stream reads, slower vessel snapshots, delta-v estimates, visual data generation |
| `mission_state.py` | Active mission registry, watchdog, mission events, abort handling, `MissionGuard` |
| `flight_recorder.py` | Current/last flight JSONL recording and summary files |
| `cameras.py` | JRTI discovery, camera URL normalization, vessel camera module fallback |
| `config.py` | Lightweight loading of `backend/.env` when present |

The backend protects the kRPC lane with locks:

- `KRPC_QUERY_LOCK` prevents idle telemetry reads from colliding with mission
  actions.
- `ACTION_LOCK` prevents overlapping action starts and tracks the active action.
- Mission registration in `mission_state.py` lets long-running routines abort
  cleanly when the active vessel disappears, changes, or appears to have been
  reverted.

## Frontend

The frontend is a React 19 and Vite application in `frontend/`.

Key pieces:

| File or Folder | Role |
| --- | --- |
| `src/App.jsx` | Main dashboard and popout routing |
| `src/data/actions.js` | UI action list mapped to backend action routes |
| `src/api/kspApi.js` | JSON API wrapper, timeouts, low-signal action error handling |
| `src/hooks/useKspPolling.js` | Polling loop for telemetry, mission status, health, action state |
| `src/components/` | Dashboard panels, action controls, backend health, telemetry views |
| `src/components/visualizations/` | p5-backed ascent/orbit/system/camera/status visualizations |
| `vite.config.js` | `/api` proxy and JRTI proxy/style override for local development |

The dashboard supports popout cards with a `?popout=...` query parameter. This
is used for dedicated displays of mission controls, vessel status, numerical
telemetry, camera feed, ascent views, and Kerbin-system map.

## Mission Actions

The UI exposes these actions from `frontend/src/data/actions.js`:

| Action ID | Label | Backend route |
| --- | --- | --- |
| `launch_rocket` | Launch Rocket | `POST /api/actions/launch_rocket` |
| `wait_one_hour` | Wait One Hour | `POST /api/actions/wait_one_hour` |
| `land_rocket` | Land Rocket | `POST /api/actions/land_rocket` |
| `flyby_mun` | Fly by Mun | `POST /api/actions/flyby_mun` |
| `circularize_at_apoapsis` | Circularize at Apoapsis | `POST /api/actions/circularize_at_apoapsis` |
| `circularize_at_periapsis` | Circularize at Periapsis | `POST /api/actions/circularize_at_periapsis` |
| `lko_tourism` | LKO Tourism | `POST /api/actions/lko_tourism` |

`launch_rocket` and `lko_tourism` accept optional JSON flags:

```json
{
  "revert_on_failure": true,
  "retry_on_revert": true
}
```

When an action starts, the backend:

1. Verifies no other action or registered mission is active.
2. Starts an action thread.
3. Takes the kRPC query lock.
4. Resets telemetry and starts flight recording.
5. Runs the maneuver or sequence.
6. Finishes the flight log, resets telemetry, releases locks, and clears action
   state.

The release button calls `POST /api/release`, aborts active mission state,
stops warp, disengages autopilot when possible, sets throttle to zero, enables
SAS, and disables RCS.

The revert button calls `POST /api/revert-to-launch`, checks whether KSP allows
revert to launch, stops warp, disengages autopilot, cuts throttle, and requests
the revert through kRPC.

## Telemetry

Telemetry is exposed at `GET /api/telemetry`. The backend starts a daemon
telemetry loop on first use and then keeps a cached snapshot updated while no
mission action owns the kRPC lane.

The telemetry payload includes:

- Orbit and flight values: altitude, surface altitude, speed, vertical speed,
  longitude, apoapsis, periapsis, time to apsides, UT, MET, situation, stage,
  throttle, available thrust, liquid fuel.
- Vessel details: name, crew count/capacity, crew control, communications,
  resource ratios, warp state.
- Delta-v estimates: practical, current pressure, sea-level, vacuum, plus
  staged profile details and launch-warning text.
- Camera snapshot data when JRTI or vessel camera modules are detected.
- Visualization-ready geometry for ascent Cartesian, ascent polar, and Kerbin
  system views.
- Cache/debug fields such as telemetry age, stream status, and visual reset
  sequence.

Slow telemetry such as resources, delta-v profiles, cameras, communications,
and system body positions is refreshed less frequently than fast stream values
to keep dashboard updates responsive.

## Camera Feeds

Camera support is configured in `backend/cameras.py` and `frontend/vite.config.js`.

By default, the backend assumes the camera stream host is the kRPC/KSP machine:

```text
http://192.168.20.104:8080/
```

If JRTI is available, the backend reads its `/cameras` endpoint and prefers
JRTI camera metadata. Otherwise, it falls back to scanning vessel parts/modules
for camera-like module names.

Production and local dev can publish JRTI paths through `/jrti` so browser
traffic stays on the same dashboard origin.

## API Reference

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/status` | Quick API and active-vessel check |
| `GET` | `/api/health` | Backend health, uptime, locks, action, mission, connection ledger, telemetry timing |
| `GET` | `/api/version` | Process and git commit metadata when available |
| `GET` | `/api/mission` | Active mission/action status and recent mission events |
| `GET` | `/api/telemetry` | Current telemetry snapshot and visualization data |
| `GET` | `/api/telemetry/last-flight-log` | Last recorded action flight log |
| `GET` | `/api/logs/last-flight` | Alias for last recorded action flight log |
| `GET` | `/api/viewports` | Recent frontend viewport reports |
| `POST` | `/api/viewports` | Store a frontend viewport report |
| `GET` | `/api/debug/krpc-benchmark` | kRPC connection/read timing benchmark, skipped while busy |
| `POST` | `/api/actions/<action_id>` | Start one mission action |
| `POST` | `/api/release` | Abort/release control of the active vessel |
| `POST` | `/api/revert-to-launch` | Ask KSP to revert the active flight to launch |

## Configuration

The backend loads `backend/.env` in development if the file exists. Production
uses `/etc/ksp-control-panel.env`.

Common settings:

```bash
KRPC_ADDRESS=192.168.20.104
KRPC_RPC_PORT=50000
KRPC_STREAM_PORT=50001
KSP_CAMERA_STREAM_URL=http://192.168.20.104:8080/
KSP_CAMERA_STREAM_KIND=iframe
KSP_CAMERA_PUBLIC_PATH_PREFIX=/jrti
KSP_BACKEND_PORT=5000
```

Frontend dev proxy setting:

```bash
KSP_API_TARGET=http://127.0.0.1:5000
```

If `KSP_API_TARGET` is not set, Vite proxies `/api` to
`http://127.0.0.1:5000`.

## Local Development

Prerequisites:

- Python 3 with `pip`
- Node.js and npm
- Kerbal Space Program running with kRPC enabled
- A readable active vessel in KSP for live telemetry
- Optional JRTI/Hullcam stream host for camera panels

Backend setup:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

There are also Windows helper scripts for the local backend:

| Script | Purpose |
| --- | --- |
| `backend/restart_backend.ps1` | Stops any process on port `5000`, starts `backend/main.py`, writes `backend/.runtime/backend.pid`, and checks `/api/status` |
| `backend/watch_backend_restart.ps1` | Runs a small local supervisor that restarts the backend when requested or if it exits |
| `backend/request_backend_restart.ps1` | Signals the supervisor to restart |
| `backend/stop_backend_supervisor.ps1` | Signals the supervisor to stop |

Frontend setup in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL shown by the frontend, usually:

```text
http://127.0.0.1:5173
```

Useful local checks:

```bash
curl http://127.0.0.1:5000/api/health
curl http://127.0.0.1:5000/api/telemetry
curl http://127.0.0.1:5000/api/mission
```

## Validation

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

Backend:

```bash
cd backend
python main.py
```

There is no dedicated automated backend test suite in this repository yet. For
backend changes, verify with `/api/health`, `/api/telemetry`, and an actual KSP
session when the change touches vessel control or kRPC behavior.

## Flight Logs

Action flight logs are stored under:

```text
backend/.runtime/telemetry_logs/
```

Files:

| File | Purpose |
| --- | --- |
| `current_flight.jsonl` | Samples for the action currently being recorded |
| `last_flight.jsonl` | Samples copied from the most recently completed action |
| `last_flight_summary.json` | Action, start/end times, duration, sample count, and error |

Read the most recent log through:

```bash
curl "http://127.0.0.1:5000/api/logs/last-flight?limit=100"
```

## Production Target

| Machine | Address | Role |
| --- | --- | --- |
| HP1 | `192.168.20.21` | KSP application host |
| KSP machine | `192.168.20.104` | KSP, kRPC, optional JRTI camera stream |

Default production paths:

| Path | Purpose |
| --- | --- |
| `/opt/ksp-control-panel/app` | Application files from the deploy package |
| `/opt/ksp-control-panel/venv` | Backend Python virtual environment |
| `/etc/ksp-control-panel.env` | Production environment file |
| `/etc/systemd/system/ksp-backend.service` | Backend systemd unit |
| `/etc/nginx/sites-available/ksp-control-panel` | Nginx site config |

## Deployment

Production updates use a package-copy-extract-apply flow. Do not use git
push-to-deploy for production updates.

From Git Bash on the dev machine:

```bash
cd C:/Users/joeps/coding/ksp_python
source deploy/aliases.sh
```

Then use:

```bash
deploy
up
down
restart
```

For first-time setup or system repair, use:

```bash
bootstrap
```

What `deploy` does:

1. `deploy/package-for-ubuntu.sh` creates
   `deploy/dist/ksp-control-panel.tar.gz`.
2. The archive is copied to HP1.
3. HP1 runs `/usr/local/sbin/ksp-control-panel-apply-deploy`.
4. The packaged `deploy/apply-deploy.sh` copies it into
   `/opt/ksp-control-panel/app`.
5. `deploy/ubuntu/deploy.sh` installs backend/frontend dependencies, builds the
   frontend, applies system config, restarts `ksp-backend`, tests Nginx, and
   reloads Nginx.

## First-Time Bootstrap

Run this on HP1 only when setting up the machine or repairing system-level
dependencies:

```bash
sudo bash deploy/ubuntu/bootstrap.sh
```

Bootstrap installs OS dependencies, creates the `ksp` deploy user, installs the
system-config helper, creates the environment file if needed, and installs the
narrow sudoers rules needed by the tar-based deploy script.

By default, bootstrap grants passwordless package application to SSH user `leo`.
Override that one-time with `DEPLOY_OPERATOR=someuser` if the HP1 SSH alias uses
a different account.

## Deployment Scripts

| Script | Runs on | Purpose |
| --- | --- | --- |
| `deploy/package-for-ubuntu.sh` | Dev machine | Creates the tar package |
| `deploy/source-deploy.sh` | Dev machine | Packages and copies the archive to HP1 |
| `deploy/manage.sh` | Dev machine | Uniform `deploy`, `up`, `down`, `restart` wrapper |
| `deploy/apply-deploy.sh` | HP1 | Extracted-package apply step |
| `deploy/ubuntu/deploy.sh` | HP1 | App build/restart step |
| `deploy/ubuntu/bootstrap.sh` | HP1 | First-time system setup |
| `deploy/ubuntu/install-system-config.sh` | HP1 | Installs/updates systemd and Nginx config |

## Post-Deploy Checks

```bash
curl http://192.168.20.21:5000/api/health
curl -I http://192.168.20.21:5173
ssh hp1 'sudo systemctl status ksp-backend --no-pager'
ssh hp1 'sudo nginx -t'
```

Also check the dashboard in a browser:

```text
http://192.168.20.21:5173
```

## Troubleshooting

No active vessel:

- Confirm KSP is running on the configured KSP machine.
- Confirm the kRPC server is enabled and listening on RPC port `50000` and
  stream port `50001`.
- Confirm there is an active, readable vessel in flight or on the pad.
- Check `/api/health` for `krpc_connections`, `last_error`, and telemetry cache
  fields.

Dashboard loads but telemetry is stale:

- Check whether `krpc_query_busy` is true in `/api/health`.
- Check `/api/mission` for an active mission/action.
- Use `/api/debug/krpc-benchmark` only when no mission action is active.

Mission action will not start:

- Only one action can run at a time.
- A registered mission holds the action lane until it finishes or is released.
- Use the dashboard release control or `POST /api/release` if a previous mission
  needs to be abandoned.

Camera feed missing:

- Confirm JRTI is reachable from the backend and browser path.
- Check `KSP_CAMERA_STREAM_URL`, `KSP_CAMERA_STREAM_KIND`, and
  `KSP_CAMERA_PUBLIC_PATH_PREFIX`.
- In local development, the Vite proxy forwards `/jrti` and related camera
  paths to `192.168.20.104:8080`.

Production deploy fails:

- Run `ssh hp1 'sudo nginx -t'`.
- Run `ssh hp1 'sudo systemctl status ksp-backend --no-pager'`.
- Verify `/etc/ksp-control-panel.env`.
- Re-run `bootstrap` only for first-time setup or system-level repair.

## Safety Notes

This project can issue real control commands to the active KSP vessel. Keep the
dashboard and kRPC server on a trusted LAN, avoid running multiple control
clients against the same active vessel, and use release/revert deliberately when
an automation no longer matches the flight state.


