"""Surveillance d'une page carrières : détecte les nouveaux liens d'offres.

robots.txt est vérifié avant chaque lecture ; si la page l'interdit, la source
est signalée en échec et rien n'est téléchargé.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from ..http import TIMEOUT, robots_allowed
from ..models import Offer, strip_html
from .base import FetchResult, Source, SourceError

MAX_DETAILS_PER_RUN = 5


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


def _clean(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path.rstrip("/"), "", ""))


class PageWatchSource(Source):
    def __init__(self, session: requests.Session, name: str, url: str, link_pattern: str,
                 assume_vie: bool = False, fetch_details: bool = False):
        super().__init__(session)
        self.name, self.url = name, url
        self.pattern = re.compile(link_pattern)
        self.require_vie = not assume_vie
        self.assume_vie = assume_vie
        self.fetch_details = fetch_details
        self._details_budget = MAX_DETAILS_PER_RUN

    def _get(self, url: str) -> str:
        try:
            if not robots_allowed(self.session, url):
                raise SourceError(f"robots.txt interdit la lecture de {url}")
            r = self.session.get(url, timeout=TIMEOUT)
        except requests.RequestException as e:
            raise SourceError(f"site injoignable : {e.__class__.__name__}") from e
        if r.status_code != 200:
            raise SourceError(f"HTTP {r.status_code} sur {url}")
        return r.text

    def fetch(self) -> FetchResult:
        parser = _Links()
        parser.feed(self._get(self.url))
        seen, offers = set(), []
        for href, text in parser.links:
            if not href or not self.pattern.search(href):
                continue
            url = _clean(urljoin(self.url, href))
            if url in seen or len(text) < 4:
                continue
            seen.add(url)
            offers.append(Offer(source=self.name, uid=url, url=url, title=text,
                                company=self.name.split("–")[0].strip(), vie_certain=self.assume_vie))
        if not offers:
            raise SourceError("aucun lien d'offre trouvé (structure de page changée ?)")
        self._details_budget = MAX_DETAILS_PER_RUN
        return FetchResult(offers, complete=True)

    def enrich(self, offer: Offer) -> bool:
        """False = pas lue faute de budget : l'offre sera réévaluée au passage suivant."""
        if not self.fetch_details or offer.description:
            return True
        if self._details_budget <= 0:
            return False
        self._details_budget -= 1
        try:
            page = self._get(offer.url)
        except (SourceError, requests.RequestException):
            return True
        page = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", page)
        offer.description = strip_html(page)[:6000]
        return True
