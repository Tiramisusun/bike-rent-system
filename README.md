# Dublin Bikes Application

## Description

Dublin Bikes Application developed as a requirement of the Software Engineering Module (2026).  
The system fetches real-time bike and weather data from external APIs, stores it in a MySQL database, and serves a React frontend through a Flask backend. It includes route planning, bike rental, user authentication, and a machine learning model for predicting bike availability.

---

## Project Structure

```
.
├── app.py                          # Flask application entry point
├── requirements.txt
├── notebooks/                      # Jupyter notebooks for ML analysis
│   └── occupancy_analysis.ipynb   # Feature selection, model comparison, best model export
├── data/
│   └── best_bike_model.pkl        # Trained RandomForest model (not tracked in git)
├── frontend/                       # React + Vite frontend
│   └── src/
│       ├── App.jsx
│       └── components/
│           ├── BikeMap.jsx              # Leaflet map with station markers
│           ├── RoutePlanner.jsx         # Route planning panel (left sidebar)
│           ├── PredictionWidget.jsx     # Bike availability prediction panel
│           ├── WeatherForecastWidget.jsx # 5-day weather forecast panel
│           ├── StationHistoryChart.jsx  # Historical availability chart modal
│           ├── StatusBar.jsx            # Bottom status bar
│           └── AppNavbar.jsx            # Top navigation bar
├── src/                            # Python backend source
│   ├── db.py                       # SQLAlchemy models & DB operations
│   ├── ml/
│   │   └── occupancy_model.py      # Model loading and prediction logic
│   ├── routes/
│   │   ├── bikes_routes.py         # /api/bikes, /api/db/stations
│   │   ├── weather_routes.py       # /api/weather, /api/weather/forecast
│   │   ├── route_planner_routes.py # /api/plan
│   │   ├── prediction_routes.py    # /api/predict
│   │   ├── auth_routes.py          # /api/auth/register, /api/auth/login
│   │   ├── rental_routes.py        # /api/rental/*
│   │   └── geocode_routes.py       # /api/geocode/eircode
│   ├── services/
│   │   ├── bikes_service.py        # JCDecaux API fetch
│   │   ├── weather_service.py      # OpenWeather API fetch
│   │   └── routing_service.py      # OSRM routing
│   └── tasks/
│       ├── bicycle/
│       │   └── stations_fetch_current.py
│       └── openweather/
│           └── fetch_current.py
├── sql/
│   ├── softwaredb.sql
│   └── bike_app.sql
├── terraform/                      # AWS infrastructure as code
├── conftest.py
├── pytest.ini
└── tests/
    ├── test_bike_api.py
    ├── test_weather_api.py
    ├── test_auth.py
    ├── test_rental.py
    ├── test_route_planner.py
    └── test_db.py
```

---

## Machine Learning

The system includes a RandomForest regression model that predicts the number of available bikes at a station given the time and weather conditions.

### Features used

| Feature | Description |
|---|---|
| `station_id` | Station identifier |
| `hour` | Hour of day (0–23) |
| `month` | Month of year |
| `year` | Year |
| `lat` / `lon` | Station coordinates |
| `day_of_week` | 0 = Monday, 6 = Sunday |
| `rush_hour` | 1 if 07:00–09:00 or 16:00–19:00 |
| `max_air_temperature_celsius` | Temperature (mapped to OpenWeather `main.temp`) |
| `air_temperature_std_deviation` | Fixed to 0 at inference |
| `max_relative_humidity_percent` | Humidity (mapped to OpenWeather `main.humidity`) |

### Training

Open `notebooks/occupancy_analysis.ipynb` and run all cells. The notebook:
1. Loads `data/final_merged_data.csv` (historical Dublin Bikes + weather data)
2. Engineers features and compares multiple algorithms (Linear Regression, Decision Tree, RandomForest, Gradient Boosting)
3. Evaluates with MAE and R²
4. Exports the best model to `data/best_bike_model.pkl`

Recommended training parameters (keeps model size under 100MB):
```python
RandomForestRegressor(n_estimators=100, max_depth=15, random_state=42)
```

### Integration

The trained model is used in two places:
- **`GET /api/predict`** — predict available bikes for any station at a given date/time
- **`GET /api/plan`** — when planning a route, the dropoff station shows predicted available stands on arrival

---

## Local Setup

### 1. Start MySQL with Podman

```bash
podman run -d \
  --name softwaredb \
  -e MYSQL_ROOT_PASSWORD=root \
  -p 3306:3306 \
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

### 2. Install Python dependencies and initialise the database

```bash
pip install -r requirements.txt
python3 src/db.py init-db
```

### 3. Start the Flask backend

```bash
python3 app.py
```

### 4. Start the React frontend

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
| `waypoints` | no | — | Intermediate stops as `lat,lng;lat,lng` |
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

# Run with coverage
python3 -m pytest --cov=src --cov-report=term-missing

# Run a specific file
python3 -m pytest tests/test_auth.py -v
```

| File | Coverage |
|---|---|
| `test_bike_api.py` | JCDecaux service, `/api/bikes`, `/api/db/stations` |
| `test_weather_api.py` | OpenWeather service, `/api/weather`, `/api/weather/forecast` |
| `test_auth.py` | Register, login, duplicate email, wrong password |
| `test_rental.py` | Full rental lifecycle, auth guard, duplicate prevention |
| `test_route_planner.py` | Haversine, penalties, `/api/plan` with/without waypoints |
| `test_db.py` | Shared fixtures reused across test files |

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
# SSH in
ssh -i ~/.ssh/your-key.pem ec2-user@<EC2_PUBLIC_IP>

# Install dependencies
sudo dnf install -y python3 python3-pip git nodejs npm

# Clone and set up
git clone https://github.com/Tiramisusun/bike-rent-system.git app
cd app
pip3 install -r requirements.txt
python3 src/db.py init-db

# Build frontend
cd frontend && npm ci && npm run build && cd ..

# Copy model file (from your local machine)
# scp -i ~/.ssh/your-key.pem data/best_bike_model.pkl ec2-user@<EC2_PUBLIC_IP>:~/app/data/

# Run
python3 app.py
```

Set up nginx to proxy port 80 → 5000, and a systemd service for auto-restart on reboot (see full instructions in deployment docs).

---

## Contributor

- Xiya Sun

