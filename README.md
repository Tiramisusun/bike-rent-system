# Dublin Bikes Application

## Description

Dublin Bikes Application developed as a requirement of the Software Engineering Module (2026).  
The system fetches real-time bike and weather data from external APIs, stores it in a MySQL database, and serves a React frontend through a Flask backend. It includes route planning, bike rental, user authentication, and a machine learning model for predicting bike availability.

---

## Project Structure

```
.
├── app.py                          # Flask application entry point
├── requirements.txt                # Python dependencies
├── conftest.py                     # Shared pytest fixtures
├── pytest.ini                      # Pytest configuration
│
├── data/                           # ML artefacts (not tracked in git)
│   ├── best_bike_model.pkl         # Trained model exported from notebook
│   ├── final_merged_data.csv       # Historical Dublin Bikes + weather data
│   └── bike_availability_time_features_updated.ipynb  # Training notebook
│
├── frontend/                       # React + Vite frontend
│   └── src/
│       ├── App.jsx                 # Root component, auth state, navbar
│       └── components/
│           ├── BikeMap.jsx              # Leaflet map, station markers, predict-all panel
│           ├── RoutePlanner.jsx         # Route planning sidebar (left)
│           ├── PredictionWidget.jsx     # Single-station prediction sidebar (left)
│           ├── WeatherForecastWidget.jsx # 5-day weather forecast sidebar (left)
│           ├── StationHistoryChart.jsx  # Historical availability chart modal
│           ├── StatusBar.jsx            # Bottom status bar
│           └── AppNavbar.jsx            # Top navigation bar
│
├── src/                            # Python backend
│   ├── db/                         # Database package (split by responsibility)
│   │   ├── __init__.py             # Re-exports all public symbols (other files unchanged)
│   │   ├── models.py               # SQLAlchemy ORM models (7 tables)
│   │   ├── engine.py               # load_engine(), init_db()
│   │   ├── writers.py              # db_from_request(), store_forecast_data()
│   │   ├── readers.py              # get_latest_weather(), get_all_stations(), etc.
│   │   └── cli.py                  # init-db CLI command
│   ├── ml/
│   │   ├── __init__.py
│   │   └── occupancy_model.py      # Model loading, feature engineering, predict()
│   ├── routes/
│   │   ├── bikes_routes.py         # GET /api/bikes, /api/db/stations
│   │   ├── weather_routes.py       # GET /api/weather, /api/weather/forecast
│   │   ├── route_planner_routes.py # GET /api/plan
│   │   ├── prediction_routes.py    # GET /api/predict, /api/predict/all
│   │   ├── auth_routes.py          # POST /api/auth/register, /api/auth/login
│   │   ├── rental_routes.py        # POST /api/rental/start|end, GET /api/rental/active|history
│   │   └── geocode_routes.py       # GET /api/geocode/eircode
│   ├── services/
│   │   ├── bikes_service.py        # JCDecaux API fetch
│   │   ├── weather_service.py      # OpenWeather API fetch
│   │   └── routing_service.py      # OSRM routing
│   └── tasks/                      # Background data-fetch tasks
│       ├── bicycle/
│       │   └── stations_fetch_current.py
│       └── openweather/
│           └── fetch_current.py
│
├── sql/                            # Database schema scripts
│   ├── softwaredb.sql
│   └── bike_app.sql
├── terraform/                      # AWS infrastructure as code
└── tests/
    ├── test_bike_api.py            # JCDecaux service & bike endpoints
    ├── test_weather_api.py         # OpenWeather service & weather endpoints
    ├── test_auth.py                # Register, login, auth guards
    ├── test_rental.py              # Full rental lifecycle & pricing
    ├── test_route_planner.py       # Haversine, scoring, /api/plan
    └── test_db.py                  # Shared DB fixtures
```

---

## Machine Learning

The system includes a RandomForest regression model that predicts the number of available bikes at a station given the time, location, and weather.

### Features used (11 total)

| Category | Features | Description |
|---|---|---|
| Station / location | `station_id`, `lat`, `lon` | Station identifier and coordinates |
| Basic time | `hour`, `month`, `year`, `day_of_week` | Calendar fields |
| Time flags | `rush_hour` | 1 during morning (7–9) and evening (16–19) peak hours |
| Weather | `max_air_temperature_celsius`, `air_temperature_std_deviation`, `max_relative_humidity_percent` | Temperature and humidity (from OpenWeather at inference; std fixed to 0) |

### Training

Open `data/bike_availability_time_features_updated.ipynb` and run all cells. The notebook:
1. Loads `data/final_merged_data.csv` (historical Dublin Bikes + weather data)
2. Engineers time and weather features
3. Compares multiple algorithms: Linear Regression, Decision Tree, RandomForest, Gradient Boosting, XGBoost
4. Evaluates with MAE and R²
5. Exports the best model to `data/best_bike_model.pkl`

### Integration

The trained model is used in three places:
- **`GET /api/predict`** — predict available bikes for a single station at a given date/time
- **`GET /api/predict/all`** — predict available bikes and free stands for all stations at once; results are shown in each station's map popup
- **`GET /api/plan`** — when planning a route, the dropoff station shows predicted available stands on arrival

---

## Local Setup

### 1. Start MySQL with Podman

```bash
podman run -d \
  --name softwaredb \
  -e MYSQL_ROOT_PASSWORD=root \
  -p 3307:3306 \
  mysql:8.0
```

Grant remote access (required for Podman's network routing):

```bash
podman exec softwaredb mysql -u root -proot -e \
  "CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY 'root'; GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION; FLUSH PRIVILEGES;"
```

Update `.env`:
```env
DB_URL=mysql+pymysql://root:root@localhost:3306/softwaredb
```

### 2. Create a Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 3. Install Python dependencies and initialise the database

```bash
pip install -r requirements.txt
python3 src/db/cli.py init-db
```

### 4. Start the Flask backend

```bash
python3 app.py
```

### 5. Start the React frontend

```bash
cd frontend
npm install
npm run dev
```

The app is available at `http://localhost:5173`. API calls are proxied to Flask on port 5000.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DB_URL` | yes | SQLAlchemy DB URL, e.g. `mysql+pymysql://root:root@localhost:3306/softwaredb` |
| `JWT_SECRET_KEY` | yes | Secret key for signing JWT tokens |
| `JCDECAUX_API_KEY` | yes | JCDecaux API key for live Dublin Bikes data |
| `JCDECAUX_CONTRACT_NAME` | yes | JCDecaux contract name (e.g. `dublin`) |
| `OPENWEATHER_API_KEY` | yes | OpenWeather API key |
| `CITY_NAME` | yes | City for weather lookup (use `Dublin,IE`) |
| `OPENCAGE_API_KEY` | no | OpenCage key for Eircode geocoding (falls back to Nominatim) |
| `FORCE_BIKE_IF_AVAILABLE` | no | `true` (default) — always recommend biking when stations are available |
| `MODEL_PATH` | no | Override path to the `.pkl` model file (defaults to `data/best_bike_model.pkl`) |

---

## API Endpoints

### Prediction

**`GET /api/predict`** — Predict available bikes at a station.

| Parameter | Required | Description |
|---|---|---|
| `station_id` | yes | Dublin Bikes station ID |
| `datetime` | no | ISO 8601 datetime (e.g. `2024-12-15T09:00`). Defaults to now. |

Response:
```json
{
  "station_id": 10,
  "station_name": "DAME STREET",
  "predicted_bikes": 8,
  "datetime": "2024-12-15T09:00:00",
  "weather": { "temp": 12.5, "humidity": 78 },
  "weather_source": "db"
}
```

Weather is read from the local database first, and falls back to the OpenWeather API if no recent data exists.

---

### Route Planning

**`GET /api/plan`** — Plan an optimal bike journey.

| Parameter | Required | Default | Description |
|---|---|---|---|
| `start_lat`, `start_lng` | yes | — | Start coordinates |
| `end_lat`, `end_lng` | yes | — | Destination coordinates |
| `max_distance_m` | no | 1500 | Max walking distance to a station (metres) |
| `candidates` | no | 4 | Candidate stations per side |

The response includes `dropoff_station.predicted_stands` — the ML model's prediction of how many stands will be free at the dropoff station when you arrive.

---

### Authentication

**`POST /api/auth/register`** — Register a new user.  
**`POST /api/auth/login`** — Log in and receive a JWT.

All protected endpoints require: `Authorization: Bearer <token>`

---

### Bike Rental

**`POST /api/rental/start`** *(JWT required)* — Start a rental. Body: `{ "station_id": 42 }`  
**`POST /api/rental/end`** *(JWT required)* — Return a bike. Body: `{ "station_id": 15 }`  
**`GET /api/rental/active`** *(JWT required)* — Get current active rental.  
**`GET /api/rental/history`** *(JWT required)* — Get completed rental history.

**Pricing:** first 30 minutes free, then €0.50 per 30-minute block (rounded up).

---

## Testing

Tests use pytest with an in-memory SQLite database — no MySQL connection required.

```bash
# Run all tests
python3 -m pytest

# Run with coverage report (shows which lines in src/ are not covered)
python3 -m pytest --cov=src --cov-report=term-missing

# Run a single file with verbose output (lists each test as PASSED or FAILED)
python3 -m pytest tests/test_auth.py -v
python3 -m pytest tests/test_prediction.py -v
```

### Test types

The test suite covers four levels:

- **Unit tests** — test individual functions in isolation (no DB, no HTTP). Examples: pricing calculation, feature engineering in `predict()`, Haversine distance, route scoring penalties.
- **Integration tests** — test a full request/response cycle through Flask, routing, and the in-memory SQLite DB. Examples: all API endpoints across auth, rental, bikes, weather, route planning, and prediction.
- **Regression tests** — the full suite acts as a regression guard; run `pytest` after any change to confirm nothing is broken.
- **Acceptance criteria** — each test maps to a user-facing requirement (e.g. first 30 minutes free, JWT required for rental, 404 for unknown station).

### Test files

| File | Type | Coverage |
|---|---|---|
| `test_auth.py` | Integration | Register, login, duplicate email, wrong password |
| `test_rental.py` | Integration | Full rental lifecycle, auth guard, duplicate prevention |
| `test_bike_api.py` | Integration | JCDecaux service, `/api/bikes`, `/api/db/stations` |
| `test_weather_api.py` | Integration | OpenWeather service, `/api/weather`, `/api/weather/forecast` |
| `test_route_planner.py` | Unit + Integration | Haversine, scoring penalties, `/api/plan` with/without waypoints |
| `test_prediction.py` | Unit + Integration | Pricing logic, feature engineering, `/api/predict`, `/api/predict/all` |
| `test_db.py` | Shared fixtures | Reused across test files |

---

## Deployment on AWS EC2

### Option A — Terraform

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Fill in db_password, jcdecaux_api_key, openweather_api_key
terraform init && terraform apply
```

Tears down with `terraform destroy`.

### Option B — Manual SSH

```bash
# SSH in (aws-flask.pem is not tracked in git — keep it secure)
ssh -i aws-flask.pem ubuntu@<EC2_PUBLIC_IP>

# Install dependencies
sudo apt-get install -y python3 python3-pip nodejs npm

# Clone and set up
git clone https://github.com/Tiramisusun/bike-rent-system.git bike-rent-system
cd bike-rent-system
pip3 install -r requirements.txt
python3 src/db/cli.py init-db

# Build frontend
cd frontend && npm ci && npm run build && cd ..

# Copy files not tracked in git (run from your local machine)
scp -i aws-flask.pem data/best_bike_model.pkl ubuntu@<EC2_PUBLIC_IP>:~/bike-rent-system/data/
scp -i aws-flask.pem .env.RDS ubuntu@<EC2_PUBLIC_IP>:~/bike-rent-system/.env

# Run
python3 app.py
```

Cron jobs are configured to keep data fresh (every 5 minutes for bikes and weather, every 60 minutes for forecast):

```
*/5  * * * * curl -s http://localhost:5000/api/bikes > /dev/null
*/5  * * * * curl -s http://localhost:5000/api/weather > /dev/null
*/60 * * * * curl -s http://localhost:5000/api/weather/forecast > /dev/null
```

---

## Contributor

- Xiya Sun

