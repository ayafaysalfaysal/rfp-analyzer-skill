"""Shared helpers: time, JSON I/O, rounding, ID handling."""
from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import math
import os
import re
import tempfile
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ID_RE = re.compile(r"^([A-Z]{1,4})-(\d{3,})$")


class RfpError(Exception):
    """A user-facing error: printed without a traceback, exit code 2."""


def now_iso() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def today() -> str:
    return _dt.date.today().isoformat()


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data) -> None:
    """Atomic JSON write (temp file + replace) so a crash never corrupts state."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_hash(obj) -> str:
    return sha256_text(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str))


def deepcopy(obj):
    return copy.deepcopy(obj)


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into a copy of base (dicts merge, everything else replaces)."""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _dec(x) -> Decimal:
    return Decimal(str(x))


def round_to(value, increment) -> float:
    """Round half-up to the nearest increment (e.g. 0.5 man-days)."""
    if value is None:
        return None
    if not increment:
        return float(value)
    q = (_dec(value) / _dec(increment)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return float(q * _dec(increment))


def round_up_to(value, increment) -> float:
    if not increment:
        return float(value)
    steps = math.ceil(float(_dec(value) / _dec(increment)) - 1e-9)
    return float(_dec(steps) * _dec(increment))


def r2(value) -> float:
    return float(_dec(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def apportion(values: dict, total, increment) -> dict:
    """Round each value to `increment` so that the rounded parts sum exactly to `total`.

    Largest-remainder method. `total` should itself be a multiple of `increment`.
    Used for client-facing tables where module figures must add up to the total.
    """
    if not values:
        return {}
    inc = _dec(increment or 1)
    units_total = int((_dec(total) / inc).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    raw_sum = sum(_dec(v) for v in values.values())
    if raw_sum == 0:
        return {k: 0.0 for k in values}
    scaled = {k: _dec(v) / raw_sum * units_total for k, v in values.items()}
    floors = {k: int(math.floor(s)) for k, s in scaled.items()}
    remaining = units_total - sum(floors.values())
    order = sorted(scaled, key=lambda k: (scaled[k] - floors[k], _dec(values[k])), reverse=True)
    for k in order[: max(remaining, 0)]:
        floors[k] += 1
    return {k: float(_dec(floors[k]) * inc) for k in values}


def fmt_num(x) -> str:
    if x is None:
        return ""
    x = float(x)
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.2f}".rstrip("0").rstrip(".")


def id_parts(ident: str):
    m = ID_RE.match(ident or "")
    if not m:
        return None
    return m.group(1), int(m.group(2))


def is_id(value) -> bool:
    return isinstance(value, str) and ID_RE.match(value) is not None


def make_id(prefix: str, number: int) -> str:
    return f"{prefix}-{number:03d}"


def as_list(x):
    if x is None or x == "":
        return []
    if isinstance(x, (list, tuple, set)):
        return list(x)
    return [x]


def join_ids(ids) -> str:
    return ", ".join(as_list(ids))


def add_working_days(start: _dt.date, days: float, working_days_per_week: int = 5) -> _dt.date:
    """Return the date on which `days` working days after `start` complete.

    Weekends beyond `working_days_per_week` are skipped. Public holidays are not
    modelled; callers must say so wherever a date is shown.
    """
    whole = int(math.ceil(days - 1e-9))
    d = start
    counted = 0
    while counted < whole:
        if d.weekday() < working_days_per_week:
            counted += 1
            if counted == whole:
                break
        d += _dt.timedelta(days=1)
    return d


def parse_date(value):
    if not value:
        return None
    if isinstance(value, _dt.date):
        return value
    return _dt.date.fromisoformat(str(value))
