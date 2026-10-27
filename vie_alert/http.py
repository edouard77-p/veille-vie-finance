"""Session HTTP commune : délais, nouvelles tentatives, respect de robots.txt."""
from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

USER_AGENT = "vie-finance-alert/1.0 (veille personnelle d'offres V.I.E ; faible frequence)"
TIMEOUT = 25


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3, connect=3, read=2, backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True, raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"})
    return s


_robots_cache: dict[str, RobotFileParser | None] = {}


def robots_allowed(session: requests.Session, url: str) -> bool:
    """True si robots.txt autorise l'URL (ou s'il n'existe pas). Lève RequestException si le site est injoignable."""
    parts = urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots_cache:
        rp = RobotFileParser()
        r = session.get(base + "/robots.txt", timeout=TIMEOUT)  # site injoignable -> exception, rien en cache
        if r.status_code in (401, 403):
            rp.disallow_all = True
        elif r.status_code >= 400:
            rp.allow_all = True
        else:
            rp.parse(r.text.splitlines())
        _robots_cache[base] = rp
    rp = _robots_cache[base]
    return rp.can_fetch(USER_AGENT, url) and rp.can_fetch("*", url)


_SECRET_ENV = ("TELEGRAM_BOT_TOKEN", "SMTP_PASSWORD", "FASTLANE_TOKEN")


def scrub(text: str) -> str:
    """Retire les secrets d'un message d'erreur (les logs d'un dépôt public sont visibles)."""
    for name in _SECRET_ENV:
        val = os.environ.get(name, "").strip()
        if val:
            text = text.replace(val, "***")
    text = re.sub(r"/bot\d+:[\w-]+", "/bot***", text)
    return re.sub(r"([?&]token=)[^&\s]+", r"\1***", text)
