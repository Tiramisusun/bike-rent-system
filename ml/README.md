# Availability model

`python -m ml.train` rebuilds `data/best_bike_model.pkl` from `data/final_merged_data.csv`
(not in git) with the notebook's preprocessing, compares candidate random forests and writes a
report to `ml/results/`. Runs in ~20 min on 2 cores; the app loads the model in `src/ml/occupancy_model.py`.

## Why not the notebook's model

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

## Known limitations

- **One month of data.** Training data is December 2024 only, so `year` and `month` are constant
  (the trees never use them) and the model has never seen another season.
- **Weak overall.** R² 0.28 on future data means time-of-day and weather explain only part of the
  variation; an average error of ~6 bikes is large for a 20–40-dock station. Recent availability
  (e.g. bikes at the same station an hour ago) would likely help far more than tuning the forest.
- **Weather feature mismatch.** Training uses short-interval max temperature and its standard
  deviation; at prediction time the app passes the current temperature and a deviation of 0.
