# Deployment Guide

## Architecture

```
Browser ──HTTP/WebSocket──▶ Apache (:80) ──reverse proxy──▶ NiceGUI/uvicorn (:8080)
```

- **Apache** handles incoming HTTP and WebSocket traffic, forwarding it to the Python app
- **NiceGUI** runs on uvicorn as a regular Python process, listening on `127.0.0.1:8080`
- **systemd** keeps the Python app running and auto-restarts on failure
- Each browser connection gets **its own session** (isolated files, options, and results)
- Concurrent extractions are **queued** (configurable via `MAX_CONCURRENT_EXTRACTIONS`)

## Quick Start: Local Testing with Docker

Test the full Apache → NiceGUI stack locally before deploying to the VM.

**Prerequisites:** Docker and Docker Compose installed.

```bash
# From the project root directory
docker compose -f deploy/docker-compose.test.yml up --build
```

Then open http://localhost in your browser.

**What to verify:**
1. UI loads correctly
2. Open two browser windows → confirm each has independent files and options
3. Upload a file and run extraction in both → second user sees "waiting in queue"
4. No WebSocket errors (check browser DevTools → Network tab, filter by "socket.io")
5. Download works after extraction

**Ports exposed:**
- `http://localhost` — via Apache reverse proxy (production-like)
- `http://localhost:8080` — direct to app (for debugging)

## Deploying to Rocky Linux VM

### Option A: Run the setup script

```bash
# Copy the project to the VM, then:
sudo bash deploy/setup.sh
```

The script is interactive and will pause for confirmation. Review each step.

### Option B: Manual steps

1. **Install dependencies:**
   ```bash
   sudo dnf install -y python3.10 python3.10-devel httpd mod_ssl gcc cmake
   ```

2. **Create service user:**
   ```bash
   sudo useradd --system --shell /sbin/nologin image-to-xlsx
   ```

3. **Deploy code to `/opt/image-to-xlsx`** and create virtualenv:
   ```bash
   cd /opt/image-to-xlsx
   python3.10 -m venv env
   env/bin/pip install -r requirements.txt --no-deps
   ```

4. **Create secrets file** at `/opt/image-to-xlsx/deploy/.env`:
   ```bash
   STORAGE_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
   echo "STORAGE_SECRET=${STORAGE_SECRET}" | sudo tee /opt/image-to-xlsx/deploy/.env
   sudo chmod 600 /opt/image-to-xlsx/deploy/.env
   ```

5. **Install and start services:**
   ```bash
   sudo cp deploy/image-to-xlsx.service /etc/systemd/system/
   sudo cp deploy/image-to-xlsx.conf /etc/httpd/conf.d/
   sudo systemctl daemon-reload
   sudo systemctl enable --now image-to-xlsx httpd
   ```

6. **Open firewall:**
   ```bash
   sudo firewall-cmd --permanent --add-service=http && sudo firewall-cmd --reload
   ```

## Configuration

All settings are via environment variables (set in `/opt/image-to-xlsx/deploy/.env`):

| Variable | Default | Description |
|---|---|---|
| `HOST` | `127.0.0.1` | Bind address for the app |
| `PORT` | `8080` | Port for the app |
| `STORAGE_SECRET` | `dev-secret-change-me` | **Must change in production.** Secret for session cookies |
| `MAX_CONCURRENT_EXTRACTIONS` | `1` | How many extractions can run simultaneously |

## Troubleshooting

**App not starting:**
```bash
sudo journalctl -u image-to-xlsx -f    # View app logs
sudo systemctl status image-to-xlsx     # Check service status
```

**Apache errors:**
```bash
sudo httpd -t                            # Test config syntax
sudo tail -f /var/log/httpd/image-to-xlsx-error.log
```

**WebSocket issues (UI loads but doesn't respond):**
- Verify Apache modules are loaded: `httpd -M | grep -E "proxy|rewrite"`
- Check that `mod_proxy_wstunnel` is enabled in `/etc/httpd/conf.modules.d/`

**Running the app directly (without Apache, for debugging):**
```bash
cd /opt/image-to-xlsx/src/image-to-xlsx
HOST=0.0.0.0 /opt/image-to-xlsx/env/bin/python -m gui
```
