# LAN Production Deployment

This app deploys to the Ubuntu server at `192.168.20.21` and connects to
KSP/kRPC on the game machine at `192.168.20.104`.

Do not use the older git push-to-deploy flow for production updates. Production
updates now use a package-copy-extract-apply flow.

## Production Shape

```text
Browser
  -> http://192.168.20.21:5173
  -> Nginx static frontend
  -> /api proxied to 127.0.0.1:5000
  -> Flask backend
  -> kRPC at 192.168.20.104:50000/50001
```

The backend intentionally runs the same Flask entrypoint in production that it
uses during development: `python main.py`. Mission state and kRPC ownership live
in process memory, and KSP exposes one active vessel control lane, so production
preserves the same single-brain behavior as local development.

## Production Paths

| Path | Purpose |
| --- | --- |
| `/opt/ksp-control-panel/app` | Application files from the deploy package |
| `/opt/ksp-control-panel/venv` | Backend Python virtual environment |
| `/etc/ksp-control-panel.env` | Production environment file |
| `/etc/systemd/system/ksp-backend.service` | Backend systemd unit |
| `/etc/nginx/sites-available/ksp-control-panel` | Nginx site config |

## Deploy

From Git Bash on the dev machine:

```bash
cd C:/Users/joeps/coding/ksp_python
source deploy/aliases.sh
```

Then use the same verbs as the other Flask/React apps:

```bash
deploy
up
down
restart
```

For first-time setup or system repair, use `bootstrap`.

What happens:

1. `deploy/package-for-ubuntu.sh` creates `deploy/dist/ksp-control-panel.tar.gz`.
2. The archive is copied to HP1.
3. HP1 runs `/usr/local/sbin/ksp-control-panel-apply-deploy`.
4. The packaged `deploy/apply-deploy.sh` copies it into `/opt/ksp-control-panel/app`.
5. `deploy/ubuntu/deploy.sh` installs dependencies, builds the frontend, applies system config, restarts `ksp-backend`, tests Nginx, and reloads Nginx.

## First-Time Bootstrap

Run this on HP1 only when setting up the machine or repairing system-level
dependencies:

```bash
sudo bash deploy/ubuntu/bootstrap.sh
```

Bootstrap installs OS dependencies, creates the `ksp` deploy user, installs the
system-config helper, creates the environment file if needed, and installs the
narrow sudoers rules needed by the package deploy flow.

By default, bootstrap grants passwordless package application to SSH user `leo`.
Override that one-time with `DEPLOY_OPERATOR=someuser` if the HP1 SSH alias uses
a different account.

## Production Config

Check or edit:

```bash
sudo nano /etc/ksp-control-panel.env
```

Expected kRPC values:

```bash
KRPC_ADDRESS=192.168.20.104
KRPC_RPC_PORT=50000
KRPC_STREAM_PORT=50001
```

Expected JRTI values if the stream is hosted on the KSP machine:

```bash
KSP_CAMERA_STREAM_URL=http://192.168.20.104:8080/
KSP_CAMERA_STREAM_KIND=iframe
KSP_CAMERA_PUBLIC_PATH_PREFIX=/jrti
```

## Scripts

| Script | Runs on | Purpose |
| --- | --- | --- |
| `deploy/package-for-ubuntu.sh` | Dev machine | Creates the tar package |
| `deploy/source-deploy.sh` | Dev machine | Packages and copies the archive to HP1 |
| `deploy/manage.sh` | Dev machine | Uniform `deploy`, `up`, `down`, `restart` wrapper |
| `deploy/apply-deploy.sh` | HP1 | Extracted-package apply step |
| `deploy/ubuntu/deploy.sh` | HP1 | Actual app build/restart step |
| `deploy/ubuntu/bootstrap.sh` | HP1 | First-time system setup |

## Health Checks

```bash
curl http://192.168.20.21:5000/api/health
curl -I http://192.168.20.21:5173
ssh hp1 'sudo systemctl status ksp-backend --no-pager'
ssh hp1 'sudo nginx -t'
```


