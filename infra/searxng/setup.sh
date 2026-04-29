#!/usr/bin/env bash
# SearXNG instance setup script for Amazon Linux 2023
# Usage: Run on a fresh EC2 instance via SSH or user-data
set -euo pipefail

echo "=== Installing Docker ==="
sudo dnf update -y
sudo dnf install -y docker htop
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker ec2-user

echo "=== Installing Docker Compose ==="
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

echo "=== Setting up SearXNG directory ==="
mkdir -p ~/searxng/searxng-config

echo "=== Generating htpasswd ==="
# Generate htpasswd for nginx basic auth
# Usage: change SEARXNG_USER and SEARXNG_PASS as needed
SEARXNG_USER="${SEARXNG_USER:-miroflow}"
SEARXNG_PASS="${SEARXNG_PASS:?Must set SEARXNG_PASS environment variable}"
echo "${SEARXNG_PASS}" | docker run --rm -i httpd:alpine htpasswd -niB "${SEARXNG_USER}" > ~/searxng/htpasswd

echo "=== Generating secret key ==="
SEARXNG_SECRET_KEY=$(openssl rand -hex 32)
echo "SEARXNG_SECRET_KEY=${SEARXNG_SECRET_KEY}" > ~/searxng/.env

echo "=== Done ==="
echo "Next steps:"
echo "  1. Copy docker-compose.yml, nginx.conf, settings.yml to ~/searxng/"
echo "  2. Copy settings.yml to ~/searxng/searxng-config/"
echo "  3. cd ~/searxng && docker compose up -d"
