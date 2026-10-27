"""État minimal, versionné dans le dépôt : offres déjà vues + santé des sources."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import STATE_DIR

try:
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo("Europe/Paris")
except Exception:  # pragma: no cover
    PARIS = timezone(timedelta(hours=1))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}   # absent ou corrompu : on repart de zéro (au pire, quelques doublons)


class State:
    MAX_PER_SOURCE = 6000
    KEEP_DAYS = 120

    def __init__(self, directory: Path = STATE_DIR):
        self.seen_path = directory / "seen.json"
        self.status_path = directory / "status.json"
        self.seen: dict[str, dict[str, str]] = _read(self.seen_path)
        self.status: dict = _read(self.status_path)
        self.status.setdefault("sources", {})

    def save(self) -> None:
        _write_atomic(self.seen_path, self.seen)
        _write_atomic(self.status_path, self.status)

    # -- offres vues -------------------------------------------------------
    def initialized(self, source: str) -> bool:
        return source in self.seen

    def is_seen(self, source: str, uid: str) -> bool:
        return uid in self.seen.get(source, {})

    def mark(self, source: str, uid: str, when: datetime | None = None) -> None:
        self.seen.setdefault(source, {}).setdefault(uid, iso(when or now_utc()))

    def prune(self, source: str, current: set[str] | None) -> None:
        """current = ensemble exhaustif en ligne (ou None si la source ne le donne pas)."""
        entries = self.seen.get(source, {})
        cutoff_recent = now_utc() - timedelta(days=3)
        cutoff_old = now_utc() - timedelta(days=self.KEEP_DAYS)

        def keep(uid: str, ts: str) -> bool:
            t = parse_iso(ts) or now_utc()
            if current is not None:
                return uid in current or t > cutoff_recent
            return t > cutoff_old

        kept = {u: t for u, t in entries.items() if keep(u, t)}
        if len(kept) > self.MAX_PER_SOURCE:
            kept = dict(sorted(kept.items(), key=lambda kv: kv[1])[-self.MAX_PER_SOURCE:])
        self.seen[source] = kept

    # -- santé des sources -----------------------------------------------
    def source_status(self, source: str) -> dict:
        return self.status["sources"].setdefault(source, {"consecutive_failures": 0, "alerted": False})

    def record_ok(self, source: str, count: int) -> dict:
        st = self.source_status(source)
        was_alerted = st.get("alerted", False)
        st.update(ok=True, last_ok=iso(now_utc()), last_count=count, consecutive_failures=0, alerted=False,
                  last_error="")
        st["recovered"] = was_alerted
        return st

    def record_fail(self, source: str, error: str) -> dict:
        st = self.source_status(source)
        st.update(ok=False, last_error=error[:300], last_fail=iso(now_utc()),
                  consecutive_failures=st.get("consecutive_failures", 0) + 1, recovered=False)
        return st

    # -- compteurs du jour (bilan quotidien) -------------------------------
    def daily(self) -> dict:
        today = now_utc().astimezone(PARIS).strftime("%Y-%m-%d")
        d = self.status.get("daily") or {}
        if d.get("date") != today:
            d = {"date": today, "runs": 0, "new_finance": 0, "notified": 0, "errors": 0}
            self.status["daily"] = d
        return d
