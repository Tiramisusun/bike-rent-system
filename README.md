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
python src/db.py init-db
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

## Contributors

Danila Macijauskas
Xiya Sun
Milo Dennehy
