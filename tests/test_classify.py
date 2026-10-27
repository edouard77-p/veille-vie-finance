import json

from vie_alert.classify import normalize


def test_normalize():
    assert normalize("Contrôleur de Gestion – FP&A") == " controleur de gestion fp&a "
    assert normalize("V.I.E.") == " v i e "


def test_finance_titles(clf, cases):
    for title, domain in cases["finance"]:
        v = clf.classify(title)
        assert v.is_finance, f"{title!r} devrait être finance ({v.reason})"
        assert v.domain == domain, f"{title!r} : {v.domain} au lieu de {domain}"
        assert v.basis == "titre"


def test_non_finance_titles(clf, cases):
    for title in cases["not_finance"]:
        v = clf.classify(title)
        assert not v.is_finance, f"{title!r} ne devrait pas être finance ({v.hits})"


def test_description_fallback(clf, cases):
    for title, desc, expected in cases["description_cases"]:
        v = clf.classify(title, desc)
        assert v.is_finance is expected, f"{title!r} / {desc[:40]!r} -> {v}"
        if expected:
            assert v.basis == "description"


def test_tags_count_as_title(clf):
    v = clf.classify("VIE Chargé de mission", tags="Finance / Comptabilité / Audit")
    assert v.is_finance and v.basis == "catégorie"


def test_vie_detection(clf, cases):
    for t in cases["vie_yes"]:
        assert clf.looks_vie(t), t
    for t in cases["vie_no"]:
        assert not clf.looks_vie(t), t


def test_keywords_file_is_valid_json_and_regex():
    from vie_alert.classify import KEYWORDS_FILE, Classifier
    data = json.loads(KEYWORDS_FILE.read_text(encoding="utf-8"))
    Classifier(data)  # compile tous les motifs : lève une erreur si un motif est invalide
    assert len(data["domaines"]) == 7
