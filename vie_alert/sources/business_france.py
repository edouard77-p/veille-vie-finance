"""Mon Volontariat International (Business France) : la source officielle des V.I.E.

On interroge l'API JSON appelée par le site lui-même (mon-vie-via.businessfrance.fr).
Elle n'est pas documentée publiquement : on reste sobre (≈10 requêtes par scan),
on relit la clé publique du site à chaque passage et on échoue proprement si le
format change, sans toucher à l'état.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re

import requests

from ..http import TIMEOUT
from ..models import Offer, strip_html
from .base import FetchResult, Source, SourceError

log = logging.getLogger(__name__)

SITE = "https://mon-vie-via.businessfrance.fr"
API_URL = os.environ.get("VIE_API_URL", "https://civiweb-api-prd.azurewebsites.net/api/Offers/search")
# Clé publique livrée à tous les navigateurs par le site (pas un identifiant personnel).
# Elle sert uniquement de secours si on n'arrive pas à la relire sur la page d'accueil.
FALLBACK_API_KEY = "l+KwpoLPiXlsjxNT/NQ2iOFz8+iuygxAODs9FeAEWYM="
PAGE_SIZE = 100   # l'API refuse au-delà
MAX_PAGES = 30
_KEY_RE = re.compile(r'[,{]API_KEY:"([^"]+)"')
_TAG_KEYS = re.compile(r"special|sector|secteur|metier|activit|domain|categor|fonction|function|job", re.I)


def offer_url(offer_id) -> str:
    return f"{SITE}/offres/{offer_id}"


def _first(raw: dict, *names, default=""):
    for n in names:
        v = raw.get(n)
        if v not in (None, "", []):
            return v
    return default


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def to_offer(raw: dict) -> Offer:
    oid = _first(raw, "id", "offerId", "Id")
    duration = _first(raw, "missionDuration", "duration")
    salary = _first(raw, "indemnite", "indemnity")
    try:
        salary = f"{int(float(salary) + 0.5):,} €/mois".replace(",", " ") if salary else ""
    except (TypeError, ValueError):
        salary = str(salary)
    tags = " ".join(s for k, v in raw.items() if _TAG_KEYS.search(k) for s in _strings(v))
    mission_type = _first(raw, "missionType", "missionTypeName", "typeMission")
    if isinstance(mission_type, dict):
        mission_type = " ".join(_strings(mission_type))
    return Offer(
        source="Business France",
        uid=str(oid),
        title=str(_first(raw, "missionTitle", "title", default="(sans titre)")).strip(),
        url=offer_url(oid),
        company=str(_first(raw, "organizationName", "companyName")).strip(),
        city=str(_first(raw, "cityName", "city")).strip().title(),
        country=str(_first(raw, "countryName", "country")).strip().title(),
        published=str(_first(raw, "startBroadcastDate", "creationDate"))[:10],
        start_date=str(_first(raw, "missionStartDate"))[:10],
        deadline=str(_first(raw, "endBroadcastDate"))[:10],
        duration=f"{duration} mois" if str(duration).isdigit() else str(duration),
        salary=salary,
        description=strip_html(" ".join(str(_first(raw, k)) for k in ("missionDescription", "missionProfile"))),
        tags=tags,
        mission_type=str(mission_type).upper(),
        vie_certain=True,
        extra={"id": oid},
    )


class BusinessFranceSource(Source):
    name = "Business France"
    require_vie = False   # tout est V.I.E / V.I.A ; le tri V.I.A se fait via include_via

    def __init__(self, session: requests.Session):
        super().__init__(session)
        self._key: str | None = None

    def _api_key(self, refresh: bool = False) -> str:
        if os.environ.get("VIE_API_KEY"):
            return os.environ["VIE_API_KEY"].strip()
        if self._key and not refresh:
            return self._key
        try:
            html = self.session.get(SITE + "/", timeout=TIMEOUT).text
            m = _KEY_RE.search(html)
            self._key = json.loads(f'"{m.group(1)}"') if m else FALLBACK_API_KEY
            if not m:
                log.warning("Clé API introuvable sur la page d'accueil : clé de secours utilisée")
        except requests.RequestException as e:
            log.warning("Page d'accueil injoignable (%s) : clé de secours utilisée", e)
            self._key = FALLBACK_API_KEY
        return self._key

    def _page(self, skip: int) -> dict:
        body = {"skip": skip, "limit": PAGE_SIZE, "sort": 0}
        for attempt in (1, 2):
            headers = {"Content-Type": "application/json", "Accept": "application/json",
                       "X-API-KEY": self._api_key(refresh=attempt == 2),
                       "Origin": SITE, "Referer": SITE + "/"}
            r = self.session.post(API_URL, json=body, headers=headers, timeout=TIMEOUT)
            if r.status_code == 401 and attempt == 1:
                continue  # clé changée : on la relit une fois
            if r.status_code != 200:
                raise SourceError(f"API Business France : HTTP {r.status_code} {r.text[:150]}")
            try:
                return r.json()
            except ValueError as e:
                raise SourceError("API Business France : réponse non JSON") from e
        raise SourceError("API Business France : clé refusée (401)")

    def fetch(self) -> FetchResult:
        raws: dict[str, dict] = {}
        total = math.inf
        for page in range(MAX_PAGES):
            data = self._page(page * PAGE_SIZE)
            batch = data if isinstance(data, list) else (data.get("result") or data.get("results"))
            if not isinstance(batch, list):
                raise SourceError("API Business France : format inattendu (pas de liste 'result')")
            count = data.get("count") if isinstance(data, dict) else None
            if isinstance(count, (int, float)) and count > 0:
                total = count
            for raw in batch:
                if raw.get("id") is not None:
                    raws[str(raw["id"])] = raw
            if len(batch) < PAGE_SIZE or len(raws) >= total:
                break
        if not raws:
            raise SourceError("API Business France : 0 offre renvoyée (on ne touche à rien)")
        complete = total is math.inf or len(raws) >= total * 0.98
        log.info("Business France : %d offres récupérées (annoncées : %s)", len(raws), total)
        return FetchResult([to_offer(r) for r in raws.values()], complete=complete)
