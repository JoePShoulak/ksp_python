# LAN Production Deployment

This app is designed to run on the Ubuntu server at `192.168.20.105` and connect
to KSP/kRPC on the game machine at `192.168.20.104`.

## Production Shape

```text
Browser
  -> http://192.168.20.105:5173
  -> Nginx static frontend
  -> /api proxied to 127.0.0.1:5000
  -> Gunicorn + Flask backend
  -> kRPC at 192.168.20.104:50000/50001
```

The backend intentionally runs as one Gunicorn worker. Mission state is stored in
process memory, so multiple workers would split action locks and telemetry state.

## Local Development

Local development still runs normally on the main machine. The backend reads
`backend/.env`, and the project default kRPC target is the LAN KSP machine:

```bash
KRPC_ADDRESS=192.168.20.104
KRPC_RPC_PORT=50000
KRPC_STREAM_PORT=50001
```

Run the backend and frontend locally however you normally do. Vite continues to
proxy `/api` to `127.0.0.1:5000` for local development; only the backend's kRPC
connection points across the LAN to KSP.

## First Server Setup

Copy or clone this repository onto the Ubuntu server, then run:

```bash
cd /path/to/ksp_python
sudo bash deploy/ubuntu/bootstrap.sh
```

The bootstrap creates:

- app directory: `/opt/ksp-control-panel/app`
- Python venv: `/opt/ksp-control-panel/venv`
- bare deployment repo: `/srv/git/ksp-control-panel.git`
- deploy user: `ksp`
- backend service: `ksp-backend`
- production env file: `/etc/ksp-control-panel.env`
- Nginx site on port `5173`

After bootstrap, check or edit:

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
```

## SSH Deploy User

The push-to-deploy remote expects SSH access as the `ksp` user. Add your public
key on the server:

```bash
sudo install -d -m 700 -o ksp -g ksp /home/ksp/.ssh
echo "YOUR_PUBLIC_KEY_HERE" | sudo tee -a /home/ksp/.ssh/authorized_keys
sudo chown ksp:ksp /home/ksp/.ssh/authorized_keys
sudo chmod 600 /home/ksp/.ssh/authorized_keys
```

## Push-To-Deploy

From your development machine:

```bash
git remote add prod ssh://ksp@192.168.20.105/srv/git/ksp-control-panel.git
git push prod main
```

The server-side hook checks out `main`, installs backend dependencies, builds
the frontend, restarts the backend service, and reloads Nginx.

## Manual Deploy

If you already have the latest code on the server:

```bash
cd /opt/ksp-control-panel/app
bash deploy/ubuntu/deploy.sh
```

## Health Checks

Backend:

```bash
curl http://127.0.0.1:5000/api/status
```

Frontend from another LAN machine:

```text
http://192.168.20.105:5173
```

Logs:

```bash
sudo journalctl -u ksp-backend -f
sudo tail -f /var/log/nginx/error.log
```

Restart services:

```bash
sudo systemctl restart ksp-backend
sudo systemctl reload nginx
```
