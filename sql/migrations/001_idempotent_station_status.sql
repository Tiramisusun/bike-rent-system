-- 001: make station_status idempotent and store station capacity.
-- Equivalent to `python -m src.db.cli migrate` (which also skips steps already applied).

-- 1. Remove duplicate snapshots, keeping the earliest row per (station_id, update_time).
DELETE s1 FROM station_status s1
JOIN station_status s2
  ON s1.station_id = s2.station_id
 AND s1.update_time = s2.update_time
 AND s1.id > s2.id;

-- 2. One row per station per JCDecaux update.
ALTER TABLE station_status
  ADD CONSTRAINT uq_station_status_station_time UNIQUE (station_id, update_time);

-- 3. Total docks per station (filled by the next ingestion run).
ALTER TABLE station ADD COLUMN bike_stands INT NULL;
