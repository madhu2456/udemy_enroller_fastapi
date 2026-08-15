#!/bin/bash
# Deployment script for Digital Ocean Droplet

set -e

echo "=== Udemy Course Enroller - Deployment Script ==="

# Variables
APP_DIR="/opt/udemy-enroller"
REPO_URL="${REPO_URL:-https://github.com/your-username/udemy-enroller.git}"

# ── Fail fast on the placeholder REPO_URL (F-ENRL-C13) ───────────────────
# Cloning the example URL would create a broken /opt/udemy-enroller checkout;
# abort before any system changes so the operator sets REPO_URL properly.
if [ "$REPO_URL" = "https://github.com/your-username/udemy-enroller.git" ]; then
    echo "ERROR: REPO_URL is still the placeholder." >&2
    echo "Set it before running, e.g. REPO_URL=https://github.com/YOUR_ORG/udemy-enroller.git ./deploy.sh" >&2
    exit 1
fi

# ── Backup cron install mode (F-ENRL-K01) ────────────────────────────────
# `./deploy.sh --install-backup-cron` installs idempotent crontab entries for
# scripts/backup_sqlite.sh + scripts/verify_backup_freshness.sh and exits.
# Host paths only; for the Docker named volume (app-data), sync the DB to the
# host first (docker compose cp web:/app/data/udemy_enroller.db
# $APP_DIR/data/udemy_enroller.db) or adjust DB_PATH below.
if [ "${1:-}" = "--install-backup-cron" ]; then
    echo "=== Installing backup cron entries (F-ENRL-K01) ==="
    if ! command -v crontab &> /dev/null; then
        echo "ERROR: crontab not found — install cron first (apt-get install -y cron)." >&2
        exit 1
    fi
    mkdir -p "$APP_DIR/backups" "$APP_DIR/data"
    BACKUP_LOG="/var/log/udemy-enroller-backup.log"
    touch "$BACKUP_LOG"

    CRON_MARKER="# udemy-enroller-backup (deploy.sh --install-backup-cron)"
    CRON_BACKUP="15 3 * * * cd $APP_DIR && DB_PATH=$APP_DIR/data/udemy_enroller.db BACKUP_DIR=$APP_DIR/backups ./scripts/backup_sqlite.sh backup >>$BACKUP_LOG 2>&1"
    CRON_FRESH="30 3 * * * BACKUP_DIR=$APP_DIR/backups MAX_AGE_HOURS=26 $APP_DIR/scripts/verify_backup_freshness.sh >>$BACKUP_LOG 2>&1"

    EXISTING="$(crontab -l 2>/dev/null || true)"
    if printf '%s\n' "$EXISTING" | grep -qF "$CRON_MARKER"; then
        echo "Backup cron already installed — nothing to do (idempotent)."
    else
        printf '%s\n' "$EXISTING" "$CRON_MARKER" "$CRON_BACKUP" "$CRON_FRESH" \
            | crontab -
        echo "Installed backup + freshness cron entries for crontab of: $(whoami)"
    fi
    echo "Log file: $BACKUP_LOG"
    echo "Manual smoke: $APP_DIR/scripts/backup_sqlite.sh drill"
    echo "See docs/ops/backup-restore.md for offsite copies and the drill log."
    exit 0
fi

echo "1. Updating system..."
apt-get update && apt-get upgrade -y

echo "2. Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
fi

echo "3. Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    apt-get install -y docker-compose-plugin
fi

echo "4. Setting up application directory..."
mkdir -p $APP_DIR
cd $APP_DIR

echo "5. Cloning/Updating repository..."
if [ -d ".git" ]; then
    git pull origin main
else
    git clone $REPO_URL .
fi

echo "6. Creating .env file (if not exists)..."
# Fernet key generation below runs on the droplet host, so install cryptography there
apt-get install -y python3-cryptography
if [ ! -f .env ]; then
    cat > .env <<EOF
SECRET_KEY=$(openssl rand -hex 32)
COOKIE_ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
DATABASE_URL=sqlite:////app/data/udemy_enroller.db
DEBUG=false
LOG_LEVEL=WARNING
HOST=0.0.0.0
PORT=8000
EOF
    echo "   .env file created with random SECRET_KEY and COOKIE_ENCRYPTION_KEY"
fi
# Restrict .env to the deploy user after any write (F-ENRL-C13)
chmod 600 .env

echo "7. Building and starting containers..."
docker compose up -d --build

echo "8. Setting up Nginx reverse proxy..."
apt-get install -y nginx

cat > /etc/nginx/sites-available/udemy-enroller <<EOF
server {
    listen 80;
    server_name _;

    # Cloudflare real-client-IP (mirrors blog_platform nginx conf.d/00-cloudflare-real-ip.conf).
    # Without this, \$remote_addr = CF edge IP and the X-Forwarded-For chain ends at the CF
    # edge, so _client_key() would key every rate-limit bucket on the edge IP (bucket collapse).
    # Ranges: https://www.cloudflare.com/ips-v4 and /ips-v6 (update periodically).
    set_real_ip_from 173.245.48.0/20;
    set_real_ip_from 103.21.244.0/22;
    set_real_ip_from 103.22.200.0/22;
    set_real_ip_from 103.31.4.0/22;
    set_real_ip_from 141.101.64.0/18;
    set_real_ip_from 108.162.192.0/18;
    set_real_ip_from 190.93.240.0/20;
    set_real_ip_from 188.114.96.0/20;
    set_real_ip_from 197.234.240.0/22;
    set_real_ip_from 198.41.128.0/17;
    set_real_ip_from 162.158.0.0/15;
    set_real_ip_from 104.16.0.0/13;
    set_real_ip_from 104.24.0.0/14;
    set_real_ip_from 172.64.0.0/13;
    set_real_ip_from 131.0.72.0/22;
    set_real_ip_from 2400:cb00::/32;
    set_real_ip_from 2606:4700::/32;
    set_real_ip_from 2803:f800::/32;
    set_real_ip_from 2405:b500::/32;
    set_real_ip_from 2405:8100::/32;
    set_real_ip_from 2a06:98c0::/29;
    set_real_ip_from 2c0f:f248::/32;
    real_ip_header CF-Connecting-IP;
    real_ip_recursive on;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
EOF

ln -sf /etc/nginx/sites-available/udemy-enroller /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo "9. Configuring firewall (ufw) — SSH + Nginx Full (80/443) only..."
# The app publishes loopback-only (127.0.0.1:8000, see docker-compose.yml), so
# the host firewall needs nothing beyond SSH + HTTP/HTTPS. Idempotent: `ufw
# allow` is a no-op on existing rules, and `--force enable` runs only when ufw
# is inactive (mirrors the Deals deploy.sh ufw pattern).
if command -v ufw &>/dev/null; then
  ufw allow OpenSSH || ufw allow 22/tcp || true
  ufw allow 'Nginx Full' || true
  if ufw status | grep -q "Status: active"; then
    echo "   ufw already active — rules verified."
  else
    ufw --force enable || true
    echo "   ufw enabled (OpenSSH, Nginx Full)."
  fi
else
  echo "   ufw not installed — skipping firewall setup."
fi

echo "10. Setting up SSL with Certbot (optional)..."
echo "   Run: certbot --nginx -d yourdomain.com"

echo ""
echo "=== Deployment Complete ==="
echo "Application is running at http://$(curl -s ifconfig.me):80"
echo "Health check: http://$(curl -s ifconfig.me)/api/health"
