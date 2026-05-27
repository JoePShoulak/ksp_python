# KSP Control Panel

KSP Control Panel deploys with the same package-copy-extract-apply pattern used
by Hypervisor. Do not use git push-to-deploy for production updates.

## Production Target

| Machine | Address | Role |
| --- | --- | --- |
| HP4 | `192.168.20.105` | KSP application host |

Default production paths:

| Path | Purpose |
| --- | --- |
| `/opt/ksp-control-panel/app` | Checked-out application files from the deploy package |
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
2. The archive is copied to HP4.
3. HP4 runs `/usr/local/sbin/ksp-control-panel-apply-deploy`.
4. The packaged `deploy/apply-deploy.sh` copies it into `/opt/ksp-control-panel/app`.
5. `deploy/ubuntu/deploy.sh` installs backend/frontend dependencies, builds the frontend, applies system config, restarts `ksp-backend`, tests Nginx, and reloads Nginx.

## First-Time Bootstrap

Run this on HP4 only when setting up the machine or repairing system-level
dependencies:

```bash
sudo bash deploy/ubuntu/bootstrap.sh
```

Bootstrap installs OS dependencies, creates the `ksp` deploy user, installs the
system-config helper, creates the environment file if needed, and installs the
narrow sudoers rules needed by the tar-based deploy script.

By default, bootstrap grants passwordless package application to SSH user `leo`.
Override that one-time with `DEPLOY_OPERATOR=someuser` if the HP4 SSH alias uses
a different account.

## Scripts

| Script | Runs on | Purpose |
| --- | --- | --- |
| `deploy/package-for-ubuntu.sh` | Dev machine | Creates the tar package |
| `deploy/source-deploy.sh` | Dev machine | Packages and copies the archive to HP4 |
| `deploy/manage.sh` | Dev machine | Uniform `deploy`, `up`, `down`, `restart` wrapper |
| `deploy/apply-deploy.sh` | HP4 | Extracted-package apply step |
| `deploy/ubuntu/deploy.sh` | HP4 | Actual app build/restart step |
| `deploy/ubuntu/bootstrap.sh` | HP4 | First-time system setup |

## Post-Deploy Checks

```bash
curl http://192.168.20.105:5000/api/health
curl -I http://192.168.20.105:5173
ssh hp4 'sudo systemctl status ksp-backend --no-pager'
ssh hp4 'sudo nginx -t'
```
