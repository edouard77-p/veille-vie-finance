from __future__ import annotations

import requests

from .ats import GreenhouseSource, LeverSource, SmartRecruitersSource, WorkdaySource
from .base import FetchResult, Source, SourceError
from .business_france import BusinessFranceSource
from .page_watch import PageWatchSource
from .rss import RssSource

__all__ = ["FetchResult", "Source", "SourceError", "BusinessFranceSource", "build_sources"]


class _Broken(Source):
    """Entrée de configuration invalide : signalée comme source en échec."""

    def __init__(self, session, name: str, error: str):
        super().__init__(session)
        self.name, self.error = name, error

    def fetch(self) -> FetchResult:
        raise SourceError(self.error)


def build_sources(cfg: dict, session: requests.Session) -> list[Source]:
    sources: list[Source] = []
    if cfg.get("business_france", {}).get("enabled", True):
        sources.append(BusinessFranceSource(session))

    builders = {
        "rss": (("url",), lambda e: RssSource(session, e["name"], e["url"], e.get("require_vie", False),
                                              e.get("require_finance", True))),
        "page_watch": (("url", "link_pattern"), lambda e: PageWatchSource(
            session, e["name"], e["url"], e["link_pattern"], e.get("assume_vie", False), e.get("fetch_details", False))),
        "workday": (("url",), lambda e: WorkdaySource(session, e["name"], e["url"], e.get("search"))),
        "greenhouse": (("board",), lambda e: GreenhouseSource(session, e["name"], e["board"])),
        "lever": (("company",), lambda e: LeverSource(session, e["name"], e["company"])),
        "smartrecruiters": (("company",), lambda e: SmartRecruitersSource(session, e["name"], e["company"])),
    }
    for kind, (required, build) in builders.items():
        for entry in cfg.get(kind, []):
            if not all(str(entry.get(k, "")).strip() for k in required):
                continue  # modèle laissé vide
            entry.setdefault("name", f"{kind} {entry.get(required[0])}")
            try:
                sources.append(build(entry))
            except Exception as e:  # regex invalide, URL mal formée, clé manquante…
                sources.append(_Broken(session, entry["name"], f"configuration invalide : {e}"))
    return sources
