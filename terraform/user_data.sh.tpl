#!/bin/bash
set -euxo pipefail
exec > /var/log/user-data.log 2>&1

# ── System packages ───────────────────────────────────────────────────────────
dnf update -y
dnf install -y python3 python3-pip git nodejs npm

# ── Clone repository ──────────────────────────────────────────────────────────
# IMPORTANT: replace with your actual GitHub repository URL
cd /home/ec2-user
git clone https://github.com/YOUR_ORG/Software-Engineering26.git app
chown -R ec2-user:ec2-user app
cd app

# ── Environment variables ─────────────────────────────────────────────────────
cat > .env <<ENVEOF
DB_URL=${db_url}
JCDECAUX_API_KEY=${jcdecaux_api_key}
JCDECAUX_CONTRACT_NAME=${jcdecaux_contract_name}
OPENWEATHER_API_KEY=${openweather_api_key}
CITY_NAME=${city_name}
FORCE_BIKE_IF_AVAILABLE=true
ENVEOF

# ── Python dependencies ───────────────────────────────────────────────────────
pip3 install -r requirements.txt

# ── Wait for RDS then initialise schema ───────────────────────────────────────
for i in $(seq 1 15); do
  python3 -c "
import pymysql, re, os
from dotenv import load_dotenv
load_dotenv()
url = os.environ['DB_URL']
m = re.search(r'://([^:]+):([^@]+)@([^:/]+):(\d+)/(\w+)', url)
pymysql.connect(host=m.group(3), port=int(m.group(4)),
                user=m.group(1), password=m.group(2), db=m.group(5)).close()
" && break || { echo "Waiting for RDS... ($i/15)"; sleep 10; }
done

python3 src/db.py init-db

# ── Build React frontend ──────────────────────────────────────────────────────
cd frontend
npm ci
npm run build
cd ..

# ── systemd service ───────────────────────────────────────────────────────────
cat > /etc/systemd/system/dublin-bikes.service <<'SVCEOF'
[Unit]
Description=Dublin Bikes Flask App
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/app
EnvironmentFile=/home/ec2-user/app/.env
ExecStart=/usr/bin/python3 app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable --now dublin-bikes

echo "=== Deployment complete ==="
