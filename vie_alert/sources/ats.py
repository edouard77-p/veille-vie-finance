"""Sites carrières hébergés sur des logiciels de recrutement à API publique.

- Greenhouse, Lever, SmartRecruiters : API publiques documentées par les éditeurs.
- Workday : le JSON que la page carrières appelle elle-même (non documenté).
Seules les offres mentionnant VIE / V.I.E / volontariat international sont gardées.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import requests

from ..http import TIMEOUT
from ..models import Offer, strip_html
from .base import FetchResult, Source, SourceError


def _json(session: requests.Session, method: str, url: str, **kw):
    try:
        r = session.request(method, url, timeout=TIMEOUT, **kw)
    except requests.RequestException as e:
        raise SourceError(f"injoignable : {e}") from e
    if r.status_code != 200:
        raise SourceError(f"HTTP {r.status_code} sur {url}")
    try:
        return r.json()
    except ValueError as e:
        raise SourceError("réponse non JSON") from e


class WorkdaySource(Source):
    """url = https://<tenant>.wdN.myworkdayjobs.com[/<langue>]/<site>"""

    def __init__(self, session, name: str, url: str, search: list[str] | None = None):
        super().__init__(session)
        self.name = name
        p = urlsplit(url)
        segs = [s for s in p.path.split("/") if s]
        if not segs or not p.netloc.endswith("myworkdayjobs.com"):
            raise SourceError(f"URL Workday invalide : {url}")
        self.site = segs[-1]
        self.tenant = p.netloc.split(".")[0]
        self.base = f"{p.scheme}://{p.netloc}"
        self.search = search or ["VIE"]
        self._details_budget = 5

    def fetch(self) -> FetchResult:
        api = f"{self.base}/wday/cxs/{self.tenant}/{self.site}/jobs"
        offers: dict[str, Offer] = {}
        for q in self.search:
            data = _json(self.session, "POST", api,
                         json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": q})
            for j in data.get("jobPostings", []):
                path = j.get("externalPath", "")
                if not path:
                    continue
                url = f"{self.base}/{self.site}{path}"
                offers[url] = Offer(source=self.name, uid=url, url=url, title=j.get("title", ""),
                                    company=self.name, city=j.get("locationsText", ""),
                                    description=" ".join(j.get("bulletFields") or []),
                                    extra={"path": path, "postedOn": j.get("postedOn", "")})
        self._details_budget = 5
        return FetchResult(list(offers.values()), complete=False)

    def enrich(self, offer: Offer) -> bool:
        """Lit la description complète d'une nouvelle offre (5 max par passage)."""
        if not offer.extra.get("path"):
            return True
        if self._details_budget <= 0:
            return False
        self._details_budget -= 1
        try:
            data = _json(self.session, "GET", f"{self.base}/wday/cxs/{self.tenant}/{self.site}{offer.extra['path']}")
        except SourceError:
            return True
        info = data.get("jobPostingInfo") or {}
        offer.description = strip_html(info.get("jobDescription", "")) or offer.description
        offer.published = str(info.get("startDate", ""))[:10] or offer.published
        offer.country = (info.get("country") or {}).get("descriptor", "") or offer.country
        return True


class GreenhouseSource(Source):
    def __init__(self, session, name: str, board: str):
        super().__init__(session)
        self.name, self.board = name, board

    def fetch(self) -> FetchResult:
        data = _json(self.session, "GET", f"https://boards-api.greenhouse.io/v1/boards/{self.board}/jobs",
                     params={"content": "true"})
        offers = [Offer(source=self.name, uid=str(j["id"]), url=j.get("absolute_url", ""), title=j.get("title", ""),
                        company=self.name, city=(j.get("location") or {}).get("name", ""),
                        published=str(j.get("updated_at", ""))[:10], description=strip_html(j.get("content", "")))
                  for j in data.get("jobs", [])]
        return FetchResult(offers, complete=True)


class LeverSource(Source):
    def __init__(self, session, name: str, company: str):
        super().__init__(session)
        self.name, self.company = name, company

    def fetch(self) -> FetchResult:
        data = _json(self.session, "GET", f"https://api.lever.co/v0/postings/{self.company}", params={"mode": "json"})
        offers = []
        for j in data if isinstance(data, list) else []:
            cat = j.get("categories") or {}
            offers.append(Offer(source=self.name, uid=j.get("id", ""), url=j.get("hostedUrl", ""), title=j.get("text", ""),
                                company=self.name, city=cat.get("location", ""),
                                description=f"{cat.get('commitment', '')} {j.get('descriptionPlain', '')}"))
        return FetchResult(offers, complete=True)


class SmartRecruitersSource(Source):
    def __init__(self, session, name: str, company: str):
        super().__init__(session)
        self.name, self.company = name, company

    def fetch(self) -> FetchResult:
        offers = []
        for q in ("VIE", "V.I.E", "volontariat"):
            data = _json(self.session, "GET", f"https://api.smartrecruiters.com/v1/companies/{self.company}/postings",
                         params={"q": q, "limit": 100})
            for j in data.get("content", []):
                loc = j.get("location") or {}
                offers.append(Offer(
                    source=self.name, uid=str(j.get("id")), title=j.get("name", ""),
                    url=f"https://jobs.smartrecruiters.com/{self.company}/{j.get('id')}",
                    company=(j.get("company") or {}).get("name", self.name),
                    city=loc.get("city", ""), country=str(loc.get("country", "")).upper(),
                    published=str(j.get("releasedDate", ""))[:10],
                    description=" ".join(str(v) for v in (j.get("typeOfEmployment") or {}).values())))
        uniq = {o.uid: o for o in offers}
        return FetchResult(list(uniq.values()), complete=False)
