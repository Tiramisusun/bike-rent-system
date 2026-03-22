# Software-Engineering26

## Description

Dublin Bikes Application developed as a requirement of Software Engineering Module (2026).
This module handles API fetch from web resources for weather and bike location, storage
and management of this data in a MySQL db, fullstack via a React frontend and via Flask backend.

## Project Structure

```
.
├── README.md
├── app.py
├── src                         # source <--- your code goes here -- python, db management etc.
│   ├── __init__.py
│   ├── common
│   │   └── placeholder.py
│   └── db.py
├── static
│   ├── placeholder.py
│   └── style.css
├── templates
│   └── index.html
├── sample-data                 # sample json fetch
└── tests                       # test-suite
    ├── test_bike_api.py        # tests for bike api fetch (Xiya)
    ├── test_db.py              # tests for DB connection, schema validation (Milo)
    └── test_weather_api.py     # tests for weather api fetch (Dan)

```

## Running MySQL with Podman

**1. Start the MySQL container:**

```bash
podman run -d \
  --name softwaredb \
  -e MYSQL_ROOT_PASSWORD=root \
  -p 3306:3306 \
  mysql:8.0
```

Then update `DB_URL` in your `.env` to match:

```env
DB_URL=mysql+pymysql://root:root@localhost:3306/softwaredb
```

**2. Grant root access from the host** (Podman routes the host as `192.168.127.1`, not `localhost`, so this is required):

```bash
podman exec softwaredb mysql -u root -proot -e \
  "CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY 'root'; GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION; FLUSH PRIVILEGES;"
```

**3. Initialize the database** (creates `softwaredb` and all tables):

```bash
source .venv/bin/activate
python3 src/db.py init-db
```

To stop/remove the container:

```bash
podman stop softwaredb && podman rm softwaredb
```

---

## Running the Frontend Locally

The frontend is a React + Vite app located in the `frontend/` directory. It proxies API requests to the Flask backend running on port 5000.

**Prerequisites:** Node.js installed

**1. Install dependencies** (first time only):

```bash
cd frontend
npm install --include=dev
```

**2. Start the Flask backend** (in a separate terminal, from the project root):

```bash
python app.py
```

**3. Start the Vite dev server:**

```bash
cd frontend
npm run dev
```

The app will be available at `http://localhost:5173`. API calls (e.g. `/api/...`) are automatically proxied to Flask at `http://localhost:5000`.

---

## Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `JCDECAUX_API_KEY` | yes | JCDecaux API key for live Dublin Bikes data |
| `JCDECAUX_CONTRACT_NAME` | yes | JCDecaux contract name (e.g. `dublin`) |
| `OPENWEATHER_API_KEY` | yes | OpenWeather API key for weather data |
| `CITY_NAME` | yes | City name for weather lookup (e.g. `Dublin`) |
| `DB_URL` | yes | SQLAlchemy database URL (e.g. `mysql+pymysql://user:pass@host/db`) |
| `GOOGLE_MAPS_API_KEY` | no | Google Maps API key (currently unused — routing uses OSRM) |
| `FORCE_BIKE_IF_AVAILABLE` | no | `true` (default) — always recommend biking when viable stations exist, skipping the walk-vs-bike travel time comparison. Set to `false` to let the service decide based on actual journey times. Useful to set `false` once route timing is validated. |

---

## API Endpoints

### Route Planner

**`GET /api/plan`** — Plan an optimal bike journey between two coordinates.

| Parameter        | Type  | Required | Default | Description                                     |
| ---------------- | ----- | -------- | ------- | ----------------------------------------------- |
| `start_lat`      | float | yes      | —       | Start latitude                                  |
| `start_lng`      | float | yes      | —       | Start longitude                                 |
| `end_lat`        | float | yes      | —       | Destination latitude                            |
| `end_lng`        | float | yes      | —       | Destination longitude                           |
| `max_distance_m` | int   | no       | 1500    | Max walking distance (metres) to/from a station |
| `candidates`     | int   | no       | 4       | Candidate stations to consider per side         |

Returns either a `"bike"` plan (pick-up station, drop-off station, walk + ride + walk times, route polylines) or a `"walk_only"` result with the reason and walk time.

**Walk timing note:** route geometry is fetched from OSRM (`router.project-osrm.org` `foot` / `cycling` profiles). The OSRM demo server's foot profile returns unrealistically fast durations, so walking times are computed from OSRM road distance ÷ 1.2 m/s (4.3 km/h) rather than OSRM's own duration field.

---

## Deployment on AWS EC2

The application runs on an EC2 instance (Flask backend + built React frontend) backed by an RDS MySQL database. Two approaches are documented below.

---

### Option A — Terraform (Infrastructure as Code)

Provisions VPC, EC2, RDS, and security groups automatically.

#### Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.3
- AWS CLI configured (`aws configure`) with an IAM user that has EC2, RDS, and VPC permissions
- An SSH key pair (`~/.ssh/id_rsa` / `~/.ssh/id_rsa.pub`)

#### Steps

**1. Copy and fill in the variables file:**

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values:

```hcl
db_password            = "a_strong_password"
jcdecaux_api_key       = "YOUR_JCDECAUX_KEY"
openweather_api_key    = "YOUR_OPENWEATHER_KEY"
```

**2. Update the GitHub repo URL in the startup script:**

Open `terraform/user_data.sh.tpl` and replace the placeholder `git clone` URL with your actual repository URL.

**3. Initialise and apply:**

```bash
terraform init
terraform plan   # review what will be created
terraform apply
```

After ~10 minutes Terraform prints:

```
app_url     = "http://<EC2_PUBLIC_IP>:5000"
ssh_command = "ssh -i ~/.ssh/id_rsa ec2-user@<EC2_PUBLIC_IP>"
```

**4. Tear down:**

```bash
terraform destroy
```

> **Cost note:** default sizing is `t3.small` EC2 + `db.t3.micro` RDS in `eu-west-1`. Remember to destroy when not in use.

---

### Option B — Manual SSH Deployment

Use this if you already have a running EC2 instance and an RDS MySQL endpoint.

#### Prerequisites

- EC2 instance running Amazon Linux 2023 (or similar), port 22 and 5000 open
- RDS MySQL 8.0 endpoint and credentials
- Your SSH key

#### Steps

**1. SSH into the instance:**

```bash
ssh -i ~/.ssh/your-key.pem ec2-user@<EC2_PUBLIC_IP>
```

**2. Install dependencies:**

```bash
sudo dnf update -y
sudo dnf install -y python3 python3-pip git nodejs npm
```

**3. Clone the repository:**

```bash
git clone https://github.com/YOUR_ORG/Software-Engineering26.git app
cd app
```

**4. Create the `.env` file:**

```bash
cat > .env <<EOF
DB_URL=mysql+pymysql://<db_user>:<db_password>@<rds_endpoint>:3306/softwaredb
JCDECAUX_API_KEY=YOUR_KEY
JCDECAUX_CONTRACT_NAME=dublin
OPENWEATHER_API_KEY=YOUR_KEY
CITY_NAME=Dublin
FORCE_BIKE_IF_AVAILABLE=true
EOF
```

**5. Install Python packages and initialise the database:**

```bash
pip3 install -r requirements.txt
python3 src/db.py init-db
```

**6. Build the React frontend:**

```bash
cd frontend
npm ci
npm run build
cd ..
```

**7. Run Flask (quick test):**

```bash
python3 app.py
```

The app is now accessible at `http://<EC2_PUBLIC_IP>:5000`.

**8. (Optional) Run as a systemd service so it survives reboots:**

```bash
sudo tee /etc/systemd/system/dublin-bikes.service > /dev/null <<'EOF'
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
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now dublin-bikes
sudo systemctl status dublin-bikes
```

---

#### Uploading local data to RDS

If you have locally collected data (CSV / SQL dumps) that needs to be seeded into RDS:

```bash
# From your local machine — copy the dump to EC2
scp -i ~/.ssh/your-key.pem data/dump.sql ec2-user@<EC2_PUBLIC_IP>:~/app/

# SSH in and import
ssh -i ~/.ssh/your-key.pem ec2-user@<EC2_PUBLIC_IP>
mysql -h <rds_endpoint> -u <db_user> -p softwaredb < ~/app/dump.sql
```

---

## Contributors

Danila Macijauskas
Xiya Sun
Milo Dennehy
