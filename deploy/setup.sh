#!/usr/bin/env bash
# ============================================================================
# Deployment script for image-to-xlsx on Rocky Linux
#
# This is a REFERENCE script. Review each step before running.
# You can run it all at once or copy-paste steps individually.
#
# Prerequisites: root/sudo access on Rocky Linux VM
# ============================================================================

set -euo pipefail

APP_DIR="/opt/image-to-xlsx"
APP_USER="image-to-xlsx"
PYTHON_VERSION="python3.10"

echo "=== Step 1: Install system dependencies ==="
sudo dnf install -y epel-release
sudo dnf install -y \
    ${PYTHON_VERSION} ${PYTHON_VERSION}-devel ${PYTHON_VERSION}-pip \
    httpd mod_ssl \
    gcc gcc-c++ cmake \
    pkg-config cairo-devel gobject-introspection-devel \
    libffi-devel openssl-devel \
    git

echo "=== Step 2: Enable required Apache modules ==="
# On Rocky Linux / RHEL, these modules are typically included with httpd.
# Verify they are loaded:
sudo httpd -M 2>/dev/null | grep -E "proxy_module|proxy_http|proxy_wstunnel|rewrite" || {
    echo "WARNING: Some required Apache modules may not be loaded."
    echo "Check /etc/httpd/conf.modules.d/ for proxy and rewrite modules."
}

echo "=== Step 3: Create service user ==="
if ! id "${APP_USER}" &>/dev/null; then
    sudo useradd --system --shell /sbin/nologin --home-dir "${APP_DIR}" "${APP_USER}"
    echo "Created user ${APP_USER}"
else
    echo "User ${APP_USER} already exists"
fi

echo "=== Step 4: Deploy application code ==="
sudo mkdir -p "${APP_DIR}"
# Copy the project files (adjust source path as needed)
# Option A: from a git clone
#   sudo git clone <repo-url> "${APP_DIR}"
# Option B: from a local copy (e.g., scp'd tarball)
#   sudo tar xzf image-to-xlsx.tar.gz -C /opt/
echo "NOTE: Copy your project files to ${APP_DIR} before continuing."
echo "The directory structure should be:"
echo "  ${APP_DIR}/src/image-to-xlsx/  (application code)"
echo "  ${APP_DIR}/deploy/            (deployment configs)"
echo "  ${APP_DIR}/requirements.txt"
read -p "Press Enter when files are in place..."

echo "=== Step 5: Create Python virtual environment ==="
cd "${APP_DIR}"
sudo ${PYTHON_VERSION} -m venv env
sudo "${APP_DIR}/env/bin/pip" install --upgrade pip
sudo "${APP_DIR}/env/bin/pip" install -r requirements.txt --no-deps

echo "=== Step 6: Create environment file for secrets ==="
if [ ! -f "${APP_DIR}/deploy/.env" ]; then
    STORAGE_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sudo tee "${APP_DIR}/deploy/.env" > /dev/null <<EOF
STORAGE_SECRET=${STORAGE_SECRET}
# HOST=127.0.0.1
# PORT=8080
# MAX_CONCURRENT_EXTRACTIONS=1
EOF
    sudo chmod 600 "${APP_DIR}/deploy/.env"
    echo "Created .env with auto-generated STORAGE_SECRET"
fi

echo "=== Step 7: Set ownership ==="
sudo chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo "=== Step 8: Install systemd service ==="
sudo cp "${APP_DIR}/deploy/image-to-xlsx.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable image-to-xlsx
sudo systemctl start image-to-xlsx
echo "Service status:"
sudo systemctl status image-to-xlsx --no-pager || true

echo "=== Step 9: Install Apache configuration ==="
sudo cp "${APP_DIR}/deploy/image-to-xlsx.conf" /etc/httpd/conf.d/
# Test Apache config syntax
sudo httpd -t
sudo systemctl enable httpd
sudo systemctl restart httpd
echo "Apache status:"
sudo systemctl status httpd --no-pager || true

echo "=== Step 10: Open firewall (if firewalld is active) ==="
if systemctl is-active --quiet firewalld; then
    sudo firewall-cmd --permanent --add-service=http
    sudo firewall-cmd --reload
    echo "Firewall updated: HTTP port 80 open"
else
    echo "firewalld not active, skipping"
fi

echo ""
echo "============================================"
echo "  Deployment complete!"
echo "  The app should be accessible at:"
echo "  http://<your-server-ip>/"
echo ""
echo "  Useful commands:"
echo "    sudo systemctl status image-to-xlsx"
echo "    sudo journalctl -u image-to-xlsx -f"
echo "    sudo systemctl restart image-to-xlsx"
echo "============================================"
