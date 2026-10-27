"""Flux RSS / Atom : Google Alerts, Talkwalker Alerts ou tout autre flux."""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import feedparser
import requests

from ..http import TIMEOUT
from ..models import Offer, strip_html
from .base import FetchResult, Source, SourceError


def unwrap(url: str) -> str:
    """Google Alerts enveloppe les liens : google.com/url?...&url=<vrai lien>."""
    parts = urlsplit(url)
    if parts.netloc.endswith("google.com") and parts.path == "/url":
        real = parse_qs(parts.query).get("url") or parse_qs(parts.query).get("q")
        if real:
            return real[0]
    return url


class RssSource(Source):
    def __init__(self, session: requests.Session, name: str, url: str,
                 require_vie: bool = False, require_finance: bool = True):
        super().__init__(session)
        self.name, self.url = name, url
        self.require_vie, self.require_finance = require_vie, require_finance

    def fetch(self) -> FetchResult:
        try:
            r = self.session.get(self.url, timeout=TIMEOUT)
        except requests.RequestException as e:
            raise SourceError(f"flux injoignable : {e}") from e
        if r.status_code != 200:
            raise SourceError(f"flux : HTTP {r.status_code}")
        feed = feedparser.parse(r.content)
        if feed.bozo and not feed.entries:
            raise SourceError(f"flux illisible : {feed.bozo_exception}")
        offers = []
        for e in feed.entries:
            link = unwrap(e.get("link", ""))
            if not link:
                continue
            published = ""
            if e.get("published_parsed") or e.get("updated_parsed"):
                t = e.get("published_parsed") or e.get("updated_parsed")
                published = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
            offers.append(Offer(
                source=self.name, uid=link, url=link,
                title=strip_html(e.get("title", "")) or link,
                description=strip_html(e.get("summary", "")),
                company=urlsplit(link).netloc.removeprefix("www."),
                published=published,
            ))
        return FetchResult(offers, complete=False)
