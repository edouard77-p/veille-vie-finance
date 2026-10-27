"""Filtre « est-ce une offre V.I.E en finance ? » + domaine financier.

Règles simples et rapides (pas d'IA) appliquées à un texte normalisé :
minuscules, sans accents, ponctuation -> espaces (sauf &). La même logique
existe en JavaScript dans apps_script/Code.gs ; les tests vérifient que les
deux donnent le même résultat.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

KEYWORDS_FILE = Path(__file__).resolve().parent.parent / "config" / "keywords.json"

GENERIC_DOMAIN = "Finance d'entreprise"   # titre « Finance … » sans précision


def normalize(text: str | None) -> str:
    """'Contrôleur de Gestion – FP&A' -> ' controleur de gestion fp&a '."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9&]+", " ", text).strip()
    return f" {text} "


def _compile(patterns: list[str]) -> re.Pattern | None:
    if not patterns:
        return None
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(f"(?:{p})" for p in patterns) + r")(?![a-z0-9])")


# « VIE » en majuscules, « V.I.E », « V.I.E. », « V I E » (jamais « vie » minuscule = le mot français).
_VIE_UPPER = re.compile(r"(?<![A-Za-z])V\.? ?I\.? ?E\.?(?![A-Za-z])")


@dataclass
class Verdict:
    is_finance: bool
    domain: str = ""
    basis: str = ""            # "titre", "catégorie", "description" ou "" si rejeté
    hits: list[str] = field(default_factory=list)
    reason: str = ""


class Classifier:
    def __init__(self, keywords: dict):
        self.domains = {name: [_compile([p]) for p in pats] for name, pats in keywords["domaines"].items()}
        self.domain_order = list(keywords["domaines"].keys())
        self.generic = [_compile([p]) for p in keywords.get("generique", [])]
        self.veto = _compile(keywords.get("veto_titre", []))
        self.desc_excl = _compile(keywords.get("exclusions_si_description_seule", []))
        self.threshold = int(keywords.get("seuil_description", 3))
        self.vie_free = _compile(keywords.get("vie_texte_libre", []))

    @classmethod
    def from_file(cls, path: Path | str = KEYWORDS_FILE) -> "Classifier":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    # -- détection --------------------------------------------------------
    def _hits(self, text_n: str) -> tuple[dict[str, list[str]], list[str]]:
        per_domain: dict[str, list[str]] = {}
        for name, regs in self.domains.items():
            found = []
            for r in regs:
                m = r.search(text_n)
                if m:
                    found.append(m.group(0).strip())
            if found:
                per_domain[name] = found
        generic = [m.group(0).strip() for r in self.generic if (m := r.search(text_n))]
        return per_domain, generic

    def _best_domain(self, per_domain: dict[str, list[str]]) -> str:
        best = max(per_domain.items(), key=lambda kv: (len(kv[1]), -self.domain_order.index(kv[0])))
        return best[0]

    def classify(self, title: str, description: str = "", tags: str = "") -> Verdict:
        title_n = normalize(title)
        if self.veto and (m := self.veto.search(title_n)):
            return Verdict(False, reason=f"veto titre : {m.group(0).strip()}")

        for label, text in (("titre", title_n), ("catégorie", normalize(tags))):
            per_domain, generic = self._hits(text)
            if per_domain:
                return Verdict(True, self._best_domain(per_domain), label,
                               sorted({h for hs in per_domain.values() for h in hs}))
            if generic:
                return Verdict(True, GENERIC_DOMAIN, label, generic)

        if self.desc_excl and (m := self.desc_excl.search(title_n)):
            return Verdict(False, reason=f"titre hors finance : {m.group(0).strip()}")

        per_domain, generic = self._hits(normalize(description))
        distinct = {h for hs in per_domain.values() for h in hs} | set(generic[:1])
        if len(distinct) >= self.threshold:
            domain = self._best_domain(per_domain) if per_domain else GENERIC_DOMAIN
            return Verdict(True, domain, "description", sorted(distinct))
        return Verdict(False, reason=f"{len(distinct)} terme(s) finance dans la description (< {self.threshold})")

    def looks_vie(self, *texts: str) -> bool:
        for t in texts:
            if not t:
                continue
            if _VIE_UPPER.search(t):
                return True
            if self.vie_free and self.vie_free.search(normalize(t)):
                return True
        return False
