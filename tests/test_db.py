import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db import init_db, get_all_stations, get_latest_weather, get_station_history
from src.db import db_from_request, Station, StationStatus


def _make_engine():
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_db(engine)
    return engine


# ── db_from_request ───────────────────────────────────────────────────────────

class TestDbFromRequest:

    def test_write_weather_creates_report(self):
        engine = _make_engine()
        payload = {
            "weather": [{"id": 800, "main": "Clear", "description": "clear sky", "icon": "01d"}],
            "main": {"temp": 12.5, "feels_like": 10.0, "humidity": 78},
            "wind": {"speed": 3.0},
            "visibility": 10000,
        }
        db_from_request(payload, typ="weather", engine=engine)
        result = get_latest_weather(engine)
        assert result is not None
        assert result["temp"] == 12.5
        assert result["humidity"] == 78

    def test_unknown_type_raises(self):
        engine = _make_engine()
        with pytest.raises(ValueError):
            db_from_request({}, typ="invalid-type", engine=engine)


# ── get_all_stations ──────────────────────────────────────────────────────────

class TestGetAllStations:

    def test_returns_all_stations(self, bike_static_data):
        engine = _make_engine()
        db_from_request(bike_static_data, typ="bike-static", engine=engine)
        assert len(get_all_stations(engine)) == 2

    def test_empty_db_returns_empty_list(self):
        engine = _make_engine()
        assert get_all_stations(engine) == []


# ── get_latest_weather ────────────────────────────────────────────────────────

class TestGetLatestWeather:

    def test_returns_most_recent(self):
        engine = _make_engine()
        old = {
            "weather": [{"id": 800, "main": "Clear", "description": "clear sky", "icon": "01d"}],
            "main": {"temp": 5.0, "feels_like": 3.0, "humidity": 60},
            "wind": {"speed": 2.0},
            "visibility": 8000,
        }
        new = {
            "weather": [{"id": 801, "main": "Clouds", "description": "few clouds", "icon": "02d"}],
            "main": {"temp": 15.0, "feels_like": 13.0, "humidity": 50},
            "wind": {"speed": 4.0},
            "visibility": 10000,
        }
        db_from_request(old, typ="weather", engine=engine)
        db_from_request(new, typ="weather", engine=engine)
        assert get_latest_weather(engine)["temp"] == 15.0


# ── get_station_history ───────────────────────────────────────────────────────

class TestGetStationHistory:

    def test_returns_records_in_ascending_order(self):
        engine = _make_engine()
        with Session(engine) as s:
            s.add(Station(station_id=5, name="TEST", contract="dublin",
                          latitude=53.34, longitude=-6.26))
            s.commit()

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with Session(engine) as s:
            s.add(StationStatus(station_id=5, avail_bikes=10, avail_bike_stands=5,
                                status="OPEN", update_time=now - timedelta(hours=2)))
            s.add(StationStatus(station_id=5, avail_bikes=6, avail_bike_stands=9,
                                status="OPEN", update_time=now - timedelta(hours=1)))
            s.add(StationStatus(station_id=5, avail_bikes=2, avail_bike_stands=13,
                                status="OPEN", update_time=now))
            s.commit()

        history = get_station_history(engine, station_id=5)
        assert len(history) == 3
        assert history[0]["avail_bikes"] == 10
        assert history[2]["avail_bikes"] == 2


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def weather_data():
    data = {
    "lat":33.44,
    "lon":-94.04,
    "timezone":"America/Chicago",
    "timezone_offset":-18000,
    "current":{
        "dt":1684929490,
        "sunrise":1684926645,
        "sunset":1684977332,
        "temp":292.55,
        "feels_like":292.87,
        "pressure":1014,
        "humidity":89,
        "dew_point":290.69,
        "uvi":0.16,
        "clouds":53,
        "visibility":10000,
        "wind_speed":3.13,
        "wind_deg":93,
        "wind_gust":6.71,
        "weather":[
            {
                "id":803,
                "main":"Clouds",
                "description":"broken clouds",
                "icon":"04d"
            }
        ]
    },
    "hourly":[
        {
            "dt":1684926000,
            "temp":292.01,
            "feels_like":292.33,
            "pressure":1014,
            "humidity":91,
            "dew_point":290.51,
            "uvi":0,
            "clouds":54,
            "visibility":10000,
            "wind_speed":2.58,
            "wind_deg":86,
            "wind_gust":5.88,
            "weather":[
                {
                "id":803,
                "main":"Clouds",
                "description":"broken clouds",
                "icon":"04n"
                }
            ],
            "pop":0.15
        }
    ],
        "alerts": [
            {
                "sender_name": "NWS Philadelphia - Mount Holly (New Jersey, Delaware, Southeastern Pennsylvania)",
                "event": "Small Craft Advisory",
                "start": 1684952747,
                "end": 1684988747,
                "description": "...SMALL CRAFT ADVISORY REMAINS IN EFFECT FROM 5 PM THIS\nAFTERNOON TO 3 AM EST FRIDAY...\n* WHAT...North winds 15 to 20 kt with gusts up to 25 kt and seas\n3 to 5 ft expected.\n* WHERE...Coastal waters from Little Egg Inlet to Great Egg\nInlet NJ out 20 nm, Coastal waters from Great Egg Inlet to\nCape May NJ out 20 nm and Coastal waters from Manasquan Inlet\nto Little Egg Inlet NJ out 20 nm.\n* WHEN...From 5 PM this afternoon to 3 AM EST Friday.\n* IMPACTS...Conditions will be hazardous to small craft."
            }
        ]
    }
    return data

@pytest.fixture
def bike_dynamic_data():
    data = {
        "number": 123,
        "contractName" : "Lyon",
        "name": "nom station",
        "address": "adresse indicative",
        "position": {
            "latitude": 45.774204,
            "longitude": 4.867512
        },
        "banking": True,
        "bonus": False,
        "status": "OPEN",
        "lastUpdate": "2019-04-08T12:23:34Z",
        "connected": True,
        "overflow": True,
        "shape": None,
        "totalStands": {
            "availabilities": {
            "bikes": 15,
            "stands": 7,
            "mechanicalBikes": 10,
            "electricalBikes": 5,
            "electricalInternalBatteryBikes": 0,
            "electricalRemovableBatteryBikes": 5
            },
            "capacity": 40
        },
        "mainStands": {
            "availabilities": {
            "bikes": 15,
            "stands": 7,
            "mechanicalBikes": 10,
            "electricalBikes": 5,
            "electricalInternalBatteryBikes": 0,
            "electricalRemovableBatteryBikes": 5
            },
            "capacity": 40
        },
        "overflowStands": None
        }
    return data


@pytest.fixture
def bike_static_data():
    data = [
        {
            "number":42,
            "name":"SMITHFIELD NORTH",
            "address":"Smithfield North",
            "latitude":53.349562,
            "longitude":-6.278198
        },
        {
            "number":30,
            "name":"PARNELL SQUARE NORTH",
            "address":"Parnell Square North",
            "latitude":53.3537415547453,
            "longitude":-6.26530144781526
         }
    ]
    return data
