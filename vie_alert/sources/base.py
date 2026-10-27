from __future__ import annotations

from dataclasses import dataclass, field

import requests

from ..models import Offer


class SourceError(RuntimeError):
    """Échec d'une source : le passage continue avec les autres."""


@dataclass
class FetchResult:
    offers: list[Offer] = field(default_factory=list)
    complete: bool = False   # True = liste exhaustive de ce qui est en ligne (autorise le nettoyage de l'état)


class Source:
    name = "source"
    require_vie = True       # l'offre doit mentionner VIE / V.I.E
    require_finance = True   # l'offre doit passer le filtre finance

    def __init__(self, session: requests.Session):
        self.session = session

    def fetch(self) -> FetchResult:  # pragma: no cover - interface
        raise NotImplementedError

    def enrich(self, offer: Offer) -> bool:
        """Complète une NOUVELLE offre (ex. lire sa description). Facultatif.

        Renvoie False si l'offre n'a pas pu être complétée faute de budget : elle
        sera alors réévaluée au passage suivant au lieu d'être marquée comme vue.
        """
        return True
