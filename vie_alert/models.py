from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def strip_html(text: str | None) -> str:
    """HTML -> texte brut sur une ligne."""
    if not text:
        return ""
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>", " ", text)
    return _SPACES.sub(" ", html.unescape(_TAGS.sub(" ", text))).strip()


@dataclass
class Offer:
    source: str                 # nom lisible de la source ("Business France", "Google Alerts", ...)
    uid: str                    # identifiant unique dans la source (id d'offre ou URL)
    title: str
    url: str
    company: str = ""
    city: str = ""
    country: str = ""
    published: str = ""         # AAAA-MM-JJ si connu
    start_date: str = ""
    deadline: str = ""
    duration: str = ""
    salary: str = ""
    description: str = ""       # texte brut
    tags: str = ""              # catégories / métiers fournis par la source
    mission_type: str = ""      # "VIE", "VIA" ou ""
    vie_certain: bool = False   # True si la source ne publie que des V.I.E
    # rempli par le classifieur
    domain: str = ""
    basis: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def location(self) -> str:
        return ", ".join(p for p in (self.city, self.country) if p)

    def short_description(self, n: int = 280) -> str:
        d = self.description.strip()
        return d if len(d) <= n else d[: n - 1].rsplit(" ", 1)[0] + "…"
