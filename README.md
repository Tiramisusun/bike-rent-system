# Software-Engineering26

## Description

Dublin Bikes Application developed as a requirement of Software Engineering Module (2026).
This module handles API fetch from web resources for weather and bike location, storage
and management of this data in a MySQL db, fullstack via a React frontend and via Flask backend.

## Project Structure

```
.
├── README.md
├── app.py                          # Flask application entry point
├── requirements.txt
├── frontend/                       # React + Vite frontend
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx
│       ├── App.css
│       ├── main.jsx
│       └── components/
│           ├── Navbar.jsx               # Top navigation bar with weather info
│           ├── BikeMap.jsx              # Leaflet map with station markers
│           ├── RoutePlanner.jsx         # Route planning panel
│           ├── StatusBar.jsx            # Bottom status bar
│           ├── StationHistoryChart.jsx  # Historical availability chart
│           └── WeatherForecast.jsx      # 5-day weather forecast modal
├── src/                            # Python backend source
│   ├── db.py                       # SQLAlchemy models & DB operations
│   ├── common/
│   │   └── config.py
│   ├── routes/
│   │   ├── bikes_routes.py              # /api/bikes, /api/db/stations endpoints
│   │   ├── weather_routes.py            # /api/weather, /api/weather/forecast endpoints
│   │   └── route_planner_routes.py      # /api/plan endpoint
│   ├── services/
│   │   ├── bikes_service.py             # JCDecaux API fetch
│   │   ├── weather_service.py           # OpenWeather API fetch
│   │   └── routing_service.py           # OSRM routing
│   └── tasks/
│       ├── bicycle/
│       │   └── stations_fetch_current.py  # Standalone bike data scraper
│       └── openweather/
│           └── fetch_current.py           # Standalone weather scraper
├── sql/
│   ├── softwaredb.sql              # Full DB dump
│   └── bike_app.sql
├── terraform/                      # AWS infrastructure as code
│   ├── main.tf
│   ├── ec2.tf
│   ├── rds.tf
│   ├── outputs.tf
│   ├── variables.tf
│   └── terraform.tfvars.example
├── conftest.py                     # pytest root config (SQLite swap, env var defaults)
├── pytest.ini                      # pytest settings
└── tests/
    ├── test_bike_api.py            # Bike service + /api/bikes endpoint tests
    ├── test_db.py                  # DB fixtures and schema data
    ├── test_weather_api.py         # Weather service + /api/weather endpoint tests
    ├── test_auth.py                # Auth endpoint tests (register, login)
    ├── test_rental.py              # Rental endpoint tests (start, end, history)
    └── test_route_planner.py       # Route planner unit + API tests
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
| `CITY_NAME` | yes | City name for weather lookup (use `Dublin,IE` to avoid matching Dublin, California) |
| `DB_URL` | yes | SQLAlchemy database URL (e.g. `mysql+pymysql://user:pass@host/db`) |
| `JWT_SECRET_KEY` | yes | Secret key used to sign JWT tokens for user authentication |
| `OPENCAGE_API_KEY` | no | OpenCage API key for accurate Irish Eircode geocoding. Free tier: 2,500 requests/day. Register at https://opencagedata.com. If unset, falls back to Nominatim. |
| `GOOGLE_MAPS_API_KEY` | no | Google Maps API key (currently unused — routing uses OSRM) |
| `FORCE_BIKE_IF_AVAILABLE` | no | `true` (default) — always recommend biking when viable stations exist, skipping the walk-vs-bike travel time comparison. Set to `false` to let the service decide based on actual journey times. |

---

## API Endpoints

### Route Planner

**`GET /api/plan`** — Plan an optimal bike journey between two coordinates, with optional waypoints.

| Parameter        | Type   | Required | Default | Description                                              |
| ---------------- | ------ | -------- | ------- | -------------------------------------------------------- |
| `start_lat`      | float  | yes      | —       | Start latitude                                           |
| `start_lng`      | float  | yes      | —       | Start longitude                                          |
| `end_lat`        | float  | yes      | —       | Destination latitude                                     |
| `end_lng`        | float  | yes      | —       | Destination longitude                                    |
| `waypoints`      | string | no       | —       | Semicolon-separated intermediate stops as `lat,lng;lat,lng` (e.g. `53.33,-6.26;53.34,-6.27`) |
| `max_distance_m` | int    | no       | 1500    | Max walking distance (metres) to/from a station          |
| `candidates`     | int    | no       | 4       | Candidate stations to consider per side                  |

Returns either a `"bike"` plan (pick-up station, drop-off station, walk + ride + walk times, route polylines) or a `"walk_only"` result with the reason and walk time.

When `waypoints` are provided the cycling leg is routed through all intermediate stops in order (`pickup → stop1 → stop2 → dropoff`) — still a single rental with one pick-up and one drop-off.

**Walk timing note:** route geometry is fetched from OSRM (`router.project-osrm.org` `foot` / `cycling` profiles). The OSRM demo server's foot profile returns unrealistically fast durations, so walking times are computed from OSRM road distance ÷ 1.2 m/s (4.3 km/h) rather than OSRM's own duration field.

---

### Geocoding

**`GET /api/geocode/eircode`** — Resolve an Irish Eircode to latitude/longitude.

| Parameter | Type   | Required | Description                              |
| --------- | ------ | -------- | ---------------------------------------- |
| `q`       | string | yes      | Eircode in canonical form, e.g. `A96 R8C4` |

Uses **OpenCage** if `OPENCAGE_API_KEY` is set in `.env`, otherwise falls back to Nominatim with an Ireland-scoped query.

**Example response:**
```json
{
  "lat": 53.2796,
  "lng": -6.1317,
  "label": "A96 R8C4, Glenageary, County Dublin, Ireland",
  "source": "opencage"
}
```

---

### Authentication

**`POST /api/auth/register`** — Create a new user account.

Request body:
```json
{ "email": "user@example.com", "password": "secret", "name": "Jane Doe" }
```

Returns `{ "token": "<JWT>", "name": "Jane Doe" }`.

**`POST /api/auth/login`** — Log in and receive a JWT.

Request body:
```json
{ "email": "user@example.com", "password": "secret" }
```

Returns `{ "token": "<JWT>", "name": "Jane Doe" }`.

All protected endpoints require the header: `Authorization: Bearer <token>`

---

### Bike Rental

**`POST /api/rental/start`** *(JWT required)* — Start a rental at a station.

Request body: `{ "station_id": 42 }`

**`POST /api/rental/end`** *(JWT required)* — Return a bike at a station.

Request body: `{ "station_id": 15 }`

Returns duration and cost. Pricing: first 30 minutes free, then €0.50 per 30-minute block.

**`GET /api/rental/active`** *(JWT required)* — Get the user's current active rental (if any).

**`GET /api/rental/history`** *(JWT required)* — Get the user's completed rental history.

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

## Testing

### Setup

Tests use **pytest** with an in-memory SQLite database — no MySQL connection required. Install test dependencies once:

```bash
pip install pytest pytest-cov
```

### Running tests

Run all tests from the project root:

```bash
python3 -m pytest
```

Run a specific test file:

```bash
python3 -m pytest tests/test_auth.py -v
python3 -m pytest tests/test_rental.py -v
python3 -m pytest tests/test_route_planner.py -v
```

Run with coverage report:

```bash
python3 -m pytest --cov=src --cov-report=term-missing
```

### How it works

The `conftest.py` at the project root runs before any test and:

1. Sets `DB_URL=sqlite:///:memory:` so tests never touch the real MySQL database
2. Patches `init_db` to skip the MySQL-specific `CREATE DATABASE` step (SQLite doesn't need it)
3. Sets dummy values for all required environment variables (`JWT_SECRET_KEY`, API keys, etc.)

Each test fixture creates its own isolated SQLite engine and seeds only the data it needs.

### Test files

| File | What it covers |
| ---- | -------------- |
| `test_bike_api.py` | Service layer (`fetch_jcdecaux_stations`): success, HTTP error, missing API key. Data format: required fields, coordinate ranges, availability non-negative, status values. Endpoints: `GET /api/bikes`, `GET /api/db/stations`, `GET /api/db/stations/<id>/history` |
| `test_weather_api.py` | Service layer (`fetch_openweather_current`, `fetch_openweather_forecast`): success, HTTP error, missing API key. Data format: temperature range, humidity percentage, description string, hourly array. Endpoints: `GET /api/weather`, `GET /api/weather/forecast` |
| `test_auth.py` | `POST /api/auth/register` and `POST /api/auth/login` — success, wrong password, duplicate email, missing fields |
| `test_rental.py` | `POST /api/rental/start`, `POST /api/rental/end`, `GET /api/rental/active`, `GET /api/rental/history` — full rental lifecycle, auth guard, duplicate rental prevention |
| `test_route_planner.py` | Unit tests for `_haversine`, `_availability_penalty`, `_walk_penalty`; integration tests for `GET /api/plan` with and without waypoints (OSRM is mocked) |
| `test_db.py` | Shared fixtures (`weather_data`, `bike_dynamic_data`, `bike_static_data`) reused across test files |

### Example output

```
tests/test_bike_api.py::TestFetchJcdecauxStations::test_returns_list_on_success  PASSED
tests/test_bike_api.py::TestFetchJcdecauxStations::test_raises_on_http_error     PASSED
tests/test_bike_api.py::TestFetchJcdecauxStations::test_raises_when_api_key_missing PASSED
tests/test_bike_api.py::TestBikeDataFormat::test_station_has_required_fields     PASSED
tests/test_bike_api.py::TestBikeDataFormat::test_position_has_lat_lng            PASSED
tests/test_bike_api.py::test_api_bikes_success                                   PASSED
tests/test_bike_api.py::test_api_bikes_upstream_error                            PASSED
tests/test_bike_api.py::test_api_db_stations_returns_list                        PASSED
tests/test_weather_api.py::TestFetchOpenweatherCurrent::test_returns_dict_on_success PASSED
tests/test_weather_api.py::TestWeatherDataFormat::test_humidity_is_percentage    PASSED
tests/test_weather_api.py::test_api_weather_success                              PASSED
tests/test_weather_api.py::test_api_weather_forecast_success                     PASSED
tests/test_route_planner.py::TestHaversine::test_same_point_is_zero              PASSED
tests/test_route_planner.py::test_plan_returns_result                            PASSED
tests/test_route_planner.py::test_plan_with_waypoints                            PASSED
tests/test_auth.py::test_register_success                                        PASSED
tests/test_auth.py::test_login_success                                           PASSED
tests/test_rental.py::test_start_rental_success                                  PASSED
tests/test_rental.py::test_cannot_start_two_rentals                              PASSED
tests/test_rental.py::test_end_rental_success                                    PASSED
55 passed in 5.49s
```

---

## Contributors

Danila Macijauskas
Xiya Sun
Milo Dennehy
