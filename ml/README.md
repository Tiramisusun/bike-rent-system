# Availability model

The app answers "how many bikes will station X have at time T?" — for the route planner that is
15–30 minutes ahead, in the prediction panel anything from minutes to days.

## Current model: trained on our own snapshots (2026-10-30)

```bash
# on the server: export the snapshots the pipeline collected (read-only)
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  psql -U airflow -d warehouse -c "\copy (select station_id, snapshot_at_utc, snapshot_at_local,
  available_bikes, available_docks, is_open, temperature_c, humidity_pct
  from intermediate.int_station_snapshot_enriched order by snapshot_at_utc) to stdout with csv header" \
  | gzip > /root/snapshots.csv.gz
# locally (≈ 2 min on 12 cores), after copying the file to data/
python -m ml.train_availability --data data/snapshots.csv.gz --since 2026-10-08
```

`--since` drops 708 sample rows from April that were loaded before continuous collection began.
The script writes `data/availability_model.pkl` (1.2 MB, not in git) and a report to `ml/results/`.

**Task.** It is now t and the station has b bikes; predict the count h minutes later, for
h = 10 min, 30 min, 1, 2, 3, 6, 12 and 24 h. Training rows: every station every 30 minutes × each
horizon, labelled with the true count at t + h (927,992 pairs from 432,828 snapshots, 113 stations,
22 days, 2026-10-08 → 10-29).

**Features** (built by `src/ml/occupancy_model.py` for both training and prediction, checked equal
by `tests/test_train_availability.py`): horizon, bikes now, capacity, change over the last hour,
the station's usual count (weekday/weekend × hour) now and at the target time, the station mean,
target hour, weekday, weekend flag, temperature and humidity. A reading older than 1 hour counts as
unknown.

**Evaluation.** The last 8 days in four 2-day windows; each model trains only on pairs whose
*target* is before the window, and the usual-count profiles come from that past only. Baselines:
*persistence* (bikes later = bikes now) and *profile* (the station's usual count at the target hour).
Selection rule, fixed before the run: the learned model with the lowest MAE averaged over horizons.

MAE in bikes, mean of the four windows ([report](results/availability-20261030-0033.json)):

| Horizon | Persistence | Profile | Gradient boosting | Gradient boosting, MAE loss | Random forest | **Served** |
|---|---|---|---|---|---|---|
| 10 min | **0.41** | 6.24 | 0.86 | 0.59 | 0.82 | **0.41** |
| 30 min | **0.93** | 6.23 | 1.27 | 1.06 | 1.28 | **0.93** |
| 1 h | **1.50** | 6.23 | 1.71 | 1.51 | 1.72 | **1.50** |
| 2 h | 2.42 | 6.22 | 2.40 | **2.25** | 2.46 | **2.25** |
| 3 h | 3.21 | 6.22 | 2.91 | **2.87** | 2.93 | **2.87** |
| 6 h | 5.22 | 6.22 | **4.04** | 4.16 | 4.29 | **4.16** |
| 12 h | 7.24 | 6.24 | 5.17 | **5.16** | 5.34 | **5.16** |
| 24 h | 6.18 | 6.22 | 5.74 | **5.66** | 5.80 | **5.66** |
| mean | 3.39 | 6.23 | 3.01 | **2.91** | 3.08 | **2.87** |

R² of the chosen model: 0.98 (10 min), 0.92 (1 h), 0.80 (3 h), 0.64 (6 h), 0.50 (12 h), 0.41 (24 h);
persistence falls to 0.29 at 6 h and −0.10 at 12 h (half a day later the daily cycle has flipped).

- **Chosen: gradient boosting with MAE loss.** It beat the random forest at every horizon, as
  XGBoost had on the old data.
- **Up to 1 hour, nothing beats "bikes now".** JCDecaux updates a station about every 10 minutes
  (median gap between `last_update`s in this data: 10.0 min; 70% of updates don't change the count),
  so the count rarely moves within the hour. From 2 hours on the model wins, by 20% at 6 h and 17%
  at 12 h over the better baseline.
- **Served = persistence up to 1 hour, the model after.** This rule was added *after* seeing the
  results above, and it is scored on the same windows, so the "Served" column is slightly optimistic.
  It is recomputed on every training run (`persistence_horizon` in `ml/train_availability.py`): from
  the shortest horizon up, persistence is kept while its MAE is no worse than the model's.

**Limitations.** Three weeks of autumn data, one public holiday (2026-10-26); each station ×
weekday/weekend × hour cell has only a few days behind it. Predictions use current weather, not the
forecast for the target time. Retrain as data accumulates — the script is meant to be re-run.

Not comparable with the numbers below: the old model was scored on different rows and features.

## Previous model: December 2024 data (2026-10-09)

`python -m ml.train` rebuilds `data/best_bike_model.pkl` from `data/final_merged_data.csv`
(not in git) with the notebook's preprocessing, compares candidate random forests and writes a
report to `ml/results/`. Runs in ~20 min on 2 cores. No longer used by the app.

### Why not the notebook's model

The notebook scored models on a shuffled 80/20 split. With 10-minute snapshots, the test set is
full of near-copies of training rows, so that split rewards memorisation. Scored on
`TimeSeriesSplit(5)` — train on the past, predict the future — the picture flips:

| Random forest | Random-split R² | **Time-series CV R²** | **Time-series CV MAE** | Size | Load |
|---|---|---|---|---|---|
| Notebook (unlimited depth, 100 trees) | 0.926 | 0.187 | 6.45 bikes | 1,092 MB | 7 s (80 s from disk in the app) |
| **Chosen: depth 12, ≥ 20 per leaf, 100 trees** | 0.654 | **0.277** | **6.21 bikes** | **24 MB** | < 0.1 s |

The selection rule was fixed before looking at results: the smallest candidate whose time-series
MAE is within 2 % of the baseline. The chosen model is 46× smaller and better on every one of the
five future folds (R² per fold 0.30 / 0.43 / 0.38 / 0.09 / 0.19 vs 0.25 / 0.38 / 0.31 / −0.05 / 0.05).
Full results: `ml/results/20261009-2235.json`.

### Known limitations

- **One month of data.** Training data is December 2024 only, so `year` and `month` are constant
  (the trees never use them) and the model has never seen another season.
- **Weak overall.** R² 0.28 on future data means time-of-day and weather explain only part of the
  variation; an average error of ~6 bikes is large for a 20–40-dock station. Recent availability
  (e.g. bikes at the same station an hour ago) would likely help far more than tuning the forest.
- **Weather feature mismatch.** Training uses short-interval max temperature and its standard
  deviation; at prediction time the app passes the current temperature and a deviation of 0.

### Early check on our own data (exploratory, 2026-10-09)

`python -m ml.explore_warehouse --data <export of intermediate.int_station_snapshot_enriched>` scores
models on what the pipeline has collected, using the app's own weather inputs. With only two days
of October 2026 data (35k snapshots), five time-series folds:

| | Mean R² | Mean MAE |
|---|---|---|
| Deployed model (trained on Dec 2024) | 0.144 | 6.65 |
| Same configuration retrained on our data | 0.458 | 4.85 |
| Baseline: each station's average from the training fold | 0.380 | 5.60 |

**Persistence baseline ("bikes later = bikes now")**, on exactly the same test rows:

| | R² | MAE |
|---|---|---|
| Last value per station before the test window (same information the models had) | **0.600** | **3.75** |
| Bikes 10 min earlier | 0.974 | 0.74 |
| Bikes 1 h earlier | 0.871 | 1.94 |
| Bikes 3 h earlier | 0.587 | 3.87 |
| Bikes at the same time yesterday (53 % of rows have it; retrained RF on those rows: 0.391) | 0.257 | 5.87 |

With the same information, persistence beats both random forests (4 of 5 folds). Up to about
three hours ahead, the current count is by far the best predictor; only for day-ahead predictions
does the time/weather model add value over "same time yesterday". So the next model should take
recent availability as a feature and must be reported against this baseline at each horizon.

The deployed model has gone stale — on current data it is worse than a per-station average.
Retraining on our own data looks better, but two days without a weekend can't support that
conclusion; revisit after ~3 weeks of collection, adding recent-availability features and a
"bikes now = bikes later" baseline. Results: `ml/results/explore-warehouse-*.json`.
