-- 002: separate forecasts from observed weather.
-- Equivalent to `python -m src.db.cli migrate` (which also skips steps already applied).
--
-- Before: every forecast entry was stored as a weather_report row (with a future
-- update_time) plus a forecast row pointing at it, re-inserted on every poll.
-- get_latest_weather() therefore returned a forecast ~5 days ahead.

-- 1. New table: one row per forecast time (created by `init_db` from the ORM model).
CREATE TABLE IF NOT EXISTS weather_forecast (
  forecast_time DATETIME NOT NULL PRIMARY KEY,
  fetched_at    DATETIME NULL,          -- NULL for rows migrated from the legacy table
  temp          FLOAT NOT NULL,
  feels_like    FLOAT NULL,
  humidity      INT NULL,
  wind_speed    FLOAT NULL,
  visibility    INT NULL,
  weather_id    INT NOT NULL,
  FOREIGN KEY (weather_id) REFERENCES weather (id)
);

-- 2. Move the latest legacy forecast for each target time.
INSERT INTO weather_forecast
  (forecast_time, fetched_at, temp, feels_like, humidity, wind_speed, visibility, weather_id)
SELECT update_time, NULL, temp, feels_like, humidity, wind_speed, visibility, weather_id
FROM (SELECT r.*, ROW_NUMBER() OVER (PARTITION BY r.update_time ORDER BY r.id DESC) rn
      FROM forecast f JOIN weather_report r ON r.id = f.report) x
WHERE rn = 1
ON DUPLICATE KEY UPDATE forecast_time = forecast_time;

-- 3. Drop the legacy table and the forecast rows it left in weather_report.
CREATE TEMPORARY TABLE legacy_forecast_reports AS SELECT DISTINCT report AS id FROM forecast;
DROP TABLE forecast;
DELETE FROM weather_report WHERE id IN (SELECT id FROM legacy_forecast_reports);

-- 4. weather_report now holds observations only, keyed on observation time.
DELETE w1 FROM weather_report w1
JOIN weather_report w2 ON w1.update_time = w2.update_time AND w1.id > w2.id;
ALTER TABLE weather_report ADD CONSTRAINT uq_weather_report_time UNIQUE (update_time);
