# Deploying to a VPS

Single server, Docker Compose. Tested on Debian 13, x86_64, 4 cores / 8 GB RAM.

```
internet ──:80──► Caddy ──► web (gunicorn: Flask + built React)
                              │ read-only
        127.0.0.1 only:  MySQL · Postgres · Airflow UI :8080   (4 DAGs write and monitor)
```

## Security baseline

- SSH: keys only (`PasswordAuthentication no`, `PermitRootLogin prohibit-password`).
- Firewall (ufw): allow 22 and 80 only. Docker-published ports bypass ufw, so every port except
  Caddy's 80 is bound to `127.0.0.1` in the compose files — that, not ufw, is what keeps them private.
- Airflow UI through an SSH tunnel: `ssh -L 8080:127.0.0.1:8080 <server>` → http://127.0.0.1:8080
- All secrets random, generated on the server, stored only in `pipelines/.env` (mode 600, never in git).
- The app refuses to start without a ≥ 32-char `JWT_SECRET_KEY`; the debugger is off (gunicorn).
- Rate limits per client IP: login 10/min and 50/h, register 5/h, everything 300/min.
- No HTTPS yet (no domain): passwords cross the network in clear text. With a domain, put it in
  `deploy/Caddyfile` instead of `:80` and Caddy obtains a certificate automatically.

## First deployment

```bash
# server, as root
apt-get update && apt-get install -y ca-certificates curl git ufw unattended-upgrades
# Docker from docker.com: https://docs.docker.com/engine/install/debian/
git clone -b data-platform https://github.com/Tiramisusun/bike-rent-system.git /opt/dublinbikes
cd /opt/dublinbikes/pipelines
cp .env.example .env && chmod 600 .env   # then set the production values below
```

Production values in `pipelines/.env` (generate each secret with `openssl rand -hex 32`):

| Variable | Value |
|---|---|
| `MYSQL_ROOT_PASSWORD`, `AIRFLOW_DB_PASSWORD`, `WAREHOUSE_PASSWORD` | random |
| `DB_URL` | `mysql+pymysql://root:<MYSQL_ROOT_PASSWORD>@mysql:3306/bike_app` |
| `JWT_SECRET_KEY`, `AIRFLOW__API_AUTH__JWT_SECRET`, `_AIRFLOW_WWW_USER_PASSWORD` | random |
| `FERNET_KEY` | `python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` |
| `JCDECAUX_API_KEY`, `OPENWEATHER_API_KEY` | your keys |
| `SMTP_*`, `ALERT_EMAIL_TO` | real mail provider, or leave `SMTP_HOST` empty to only log alerts |

```bash
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
$COMPOSE up -d mysql                       # empty bike_app database
# optional: load existing data (mysqldump without the user table's rows)
$COMPOSE exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" bike_app' < bike_app.sql
$COMPOSE up -d --build                     # migrations + warehouse setup run in airflow-init
for d in ingest forecast transform monitor; do
  $COMPOSE exec airflow-scheduler airflow dags unpause dublinbikes_$d
done
```

## Updating

```bash
cd /opt/dublinbikes && git pull
cd pipelines && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```
