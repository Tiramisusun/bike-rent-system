"""Execution-accuracy scoring: does the agent's result set match the gold result set?

Equivalent SQL can be written many ways, so results are compared, not SQL text.
Deliberately lenient where the answer is the same, strict where it isn't:

- extra columns are fine (asked "which station", returned name *and* value);
  every gold column must match some predicted column
- column order never matters; row order only when the question asks for a ranking
- numbers match within 1% (31.97 vs 31.973913); a ratio may be given as a
  percentage (0.1426 vs 14.26)
- the number of rows must match exactly (top 3 is not top 1)
"""

import math


def _norm(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        try:
            return float(s)
        except ValueError:
            return s.lower()
    return str(value).lower()


def _eq(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=0.01, abs_tol=0.01)
    return a == b


def _sort_key(v):
    # Numbers sort by a coarse rounding so values within tolerance stay aligned.
    return (0, round(v, 1)) if isinstance(v, float) else (1, "" if v is None else str(v))


def _same_multiset(a: list, b: list) -> bool:
    return len(a) == len(b) and all(
        _eq(x, y) for x, y in zip(sorted(a, key=_sort_key), sorted(b, key=_sort_key)))


def _scale(v, factor: float):
    return v * factor if isinstance(v, float) else v


def results_match(gold_rows: list[list], pred_rows: list[list], order_matters: bool = False) -> bool:
    gold = [[_norm(v) for v in r] for r in gold_rows]
    pred = [[_norm(v) for v in r] for r in pred_rows]
    if len(gold) != len(pred):
        return False
    if not gold:
        return True
    if len(pred[0]) < len(gold[0]):
        return False

    # Map each gold column to an unused predicted column holding the same values
    # (allowing a ratio <-> percentage rescale for numeric columns).
    mapping, used = [], set()
    for j in range(len(gold[0])):
        gold_col = [r[j] for r in gold]
        match = next(
            ((k, f) for k in range(len(pred[0])) if k not in used
             for f in (1.0, 0.01, 100.0)
             if _same_multiset(gold_col, [_scale(r[k], f) for r in pred])),
            None,
        )
        if match is None:
            return False
        mapping.append(match)
        used.add(match[0])

    projected = [[_scale(r[k], f) for k, f in mapping] for r in pred]
    if not order_matters:
        row_key = lambda row: tuple(_sort_key(v) for v in row)
        gold, projected = sorted(gold, key=row_key), sorted(projected, key=row_key)
    return all(_eq(a, b) for g, p in zip(gold, projected) for a, b in zip(g, p))
