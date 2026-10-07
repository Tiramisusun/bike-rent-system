"""Raw JSON archive, partitioned by date: <root>/<source>/date=YYYY-MM-DD/<source>_HHMMSS.json

The archive is the source of truth for replays: loaders read from these files,
never from the API directly, so any day can be reloaded after a schema change.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw"


def raw_root() -> Path:
    return Path(os.getenv("RAW_DATA_DIR", str(_DEFAULT_ROOT)))


def raw_path(source: str, fetched_at: datetime, root: Optional[Path] = None) -> Path:
    root = root or raw_root()
    return (
        root / source / f"date={fetched_at:%Y-%m-%d}"
        / f"{source}_{fetched_at:%H%M%S}.json"
    )


def save_raw(source: str, payload: Any, fetched_at: Optional[datetime] = None,
             root: Optional[Path] = None) -> Path:
    """Write payload atomically (tmp file + rename) and return its path."""
    fetched_at = fetched_at or datetime.now(timezone.utc)
    path = raw_path(source, fetched_at, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False))
    tmp.replace(path)
    return path


def fetched_at_from_path(path: str | Path) -> datetime:
    """Recover the (naive UTC) fetch time encoded in a raw file path.

    Lets a replay of an old file reproduce exactly what the original load wrote.
    """
    path = Path(path)
    day = path.parent.name.removeprefix("date=")
    hms = path.stem.rsplit("_", 1)[-1]
    return datetime.strptime(f"{day} {hms}", "%Y-%m-%d %H%M%S")


def load_raw(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())
