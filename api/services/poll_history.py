"""Rolling 7-day poll duration history store (file-backed, no schema migration)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from nightfall_photo_ingress.status import STATUS_FILE_PATH

_HISTORY_FILE_PATH = STATUS_FILE_PATH.parent / "photo-ingress-poll-history.jsonl"

_DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _read_entries(path: Path) -> list[dict]:
    """Read all JSONL entries from the history file; tolerates malformed lines."""
    if not path.exists():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
    return entries


def _write_entries(path: Path, entries: list[dict]) -> None:
    """Atomically rewrite the history file with the given entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _record_current_poll(
    *,
    status_path: Path = STATUS_FILE_PATH,
    history_path: Path = _HISTORY_FILE_PATH,
) -> None:
    """Append current status file's poll duration to history (idempotent by ts)."""
    if not status_path.exists():
        return
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
        ts = data.get("updated_at")
        raw_dur = data.get("details", {}).get("poll_duration_s")
        if not isinstance(ts, str) or not isinstance(raw_dur, (int, float)):
            return
        duration_s = float(raw_dur)
    except (json.JSONDecodeError, OSError, AttributeError):
        return

    entries = _read_entries(history_path)
    if any(e.get("ts") == ts for e in entries):
        return  # already recorded

    entries.append({"ts": ts, "duration_s": duration_s})

    # Prune entries older than 8 days to stay compact
    cutoff = (datetime.now(UTC) - timedelta(days=8)).strftime("%Y-%m-%d")
    entries = [e for e in entries if e.get("ts", "")[:10] >= cutoff]

    _write_entries(history_path, entries)


def get_poll_history_7days(
    *,
    status_path: Path = STATUS_FILE_PATH,
    history_path: Path = _HISTORY_FILE_PATH,
) -> list[dict]:
    """Return last 7 days of poll durations as [{"day": "Mon", "duration_s": float}, ...].

    Missing days are filled with duration_s=0.  Days are returned in chronological
    order (oldest first), labelled Mon–Sun matching the actual calendar day.
    """
    _record_current_poll(status_path=status_path, history_path=history_path)

    today = datetime.now(UTC).date()
    days = [today - timedelta(days=6 - i) for i in range(7)]

    entries = _read_entries(history_path)

    # Index by date string; most recent entry per day wins
    by_date: dict[str, float] = {}
    for e in entries:
        ts = e.get("ts", "")
        dur = e.get("duration_s")
        if not isinstance(dur, (int, float)):
            continue
        date_str = ts[:10]
        by_date[date_str] = float(dur)

    return [
        {"day": _DAY_LABELS[d.weekday()], "duration_s": by_date.get(d.isoformat(), 0.0)}
        for d in days
    ]
