#!/bin/bash
# Deployment script for Digital Ocean Droplet

set -e

echo "=== Udemy Course Enroller - Deployment Script ==="

# Variables
APP_DIR="/opt/udemy-enroller"
REPO_URL="${REPO_URL:-https://github.com/your-username/udemy-enroller.git}"

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
if [ ! -f .env ]; then
    cat > .env <<EOF
SECRET_KEY=$(openssl rand -hex 32)
DATABASE_URL=sqlite:////app/data/udemy_enroller.db
DEBUG=false
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000
EOF
    echo "   .env file created with random SECRET_KEY"
fi

echo "7. Building and starting containers..."
docker compose up -d --build

echo "8. Setting up Nginx reverse proxy..."
apt-get install -y nginx

cat > /etc/nginx/sites-available/udemy-enroller <<EOF
server {
    listen 80;
    server_name _;

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

echo "9. Setting up SSL with Certbot (optional)..."
echo "   Run: certbot --nginx -d yourdomain.com"

echo ""
echo "=== Deployment Complete ==="
echo "Application is running at http://$(curl -s ifconfig.me):80"
echo "Health check: http://$(curl -s ifconfig.me)/api/health"
