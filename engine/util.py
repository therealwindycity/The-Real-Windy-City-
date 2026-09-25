"""Small shared helpers: config loading, time, hashing."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.getenv("REAPER_CONFIG_DIR", ROOT / "config"))


def data_dir() -> Path:
    """Resolved at call time so tests/demo can redirect via REAPER_DATA_DIR."""
    return Path(os.getenv("REAPER_DATA_DIR", ROOT / "data"))


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def now_iso() -> str:
    return now().isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    v = value.strip().replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            d = dt.datetime.fromisoformat(v) if fmt is None else dt.datetime.strptime(v[:26], fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
            return d
        except ValueError:
            continue
    return None


def sha256(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def short_id(*parts: str, prefix: str = "evt_") -> str:
    return prefix + sha256("|".join(parts))[:10]


def load_json(name: str) -> dict:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def load_config() -> dict:
    cfg = load_json("jurisdictions.json")
    cfg["watchlist"] = load_json("watchlist.json")
    return cfg


def clean_ws(text: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n\n", text or "")).strip()
