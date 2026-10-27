"""Lecture de l'état de la voie rapide (Apps Script) : santé + offres déjà envoyées."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import requests

from .config import Secrets
from .http import scrub
from .state import now_utc, parse_iso

log = logging.getLogger(__name__)


@dataclass
class FastlaneStatus:
    reachable: bool
    last_bf_scan: datetime | None = None
    bf_ok: bool = False
    sent_ids: set[str] = field(default_factory=set)
    error: str = ""

    def healthy(self, stale_minutes: int) -> bool:
        if not (self.reachable and self.bf_ok and self.last_bf_scan):
            return False
        return (now_utc() - self.last_bf_scan).total_seconds() < stale_minutes * 60

    def describe(self) -> str:
        if not self.reachable:
            return f"injoignable ({self.error})"
        if not self.last_bf_scan:
            return "aucun scan enregistré"
        mins = int((now_utc() - self.last_bf_scan).total_seconds() // 60)
        return f"dernier scan Business France il y a {mins} min" + ("" if self.bf_ok else " (en échec)")


def fetch_status(secrets: Secrets, session: requests.Session) -> FastlaneStatus | None:
    if not secrets.fastlane_url:
        return None
    try:
        r = session.get(secrets.fastlane_url, params={"token": secrets.fastlane_token}, timeout=30)
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        return FastlaneStatus(False, error=scrub(str(e))[:120])
    if not data.get("ok"):
        return FastlaneStatus(False, error=str(data.get("error", f"HTTP {r.status_code}"))[:120])
    return FastlaneStatus(
        reachable=True,
        last_bf_scan=parse_iso(data.get("lastBfScan")),
        bf_ok=bool(data.get("bfOk")),
        sent_ids={str(x) for x in data.get("sentIds", [])},
    )
