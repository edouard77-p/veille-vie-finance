import pytest

from conftest import FIXTURES, FakeResponse, FakeSession, bf_raw
from vie_alert import http as vhttp
from vie_alert.sources import SourceError, build_sources
from vie_alert.sources.ats import WorkdaySource
from vie_alert.sources.business_france import API_URL, BusinessFranceSource, to_offer
from vie_alert.sources.page_watch import PageWatchSource
from vie_alert.sources.rss import RssSource, unwrap

HOME = '<html><script>window.__NUXT__={config:{public:{API_KEY:"abc\\u002Fdef=",x:1}}}</script></html>'


def bf_route(total=120, key="abc/def=", fail_first_with_401=False):
    state = {"401_sent": False}

    def route(method, url, kw):
        if method == "GET":
            return FakeResponse(text=HOME)
        assert url == API_URL
        if kw["headers"]["X-API-KEY"] != key:
            return FakeResponse(401, text="unauthorized")
        if fail_first_with_401 and not state["401_sent"]:
            state["401_sent"] = True
            return FakeResponse(401, text="unauthorized")
        skip, limit = kw["json"]["skip"], kw["json"]["limit"]
        ids = range(skip, min(skip + limit, total))
        return FakeResponse(body={"count": total, "result": [bf_raw(1000 + i) for i in ids]})
    return route


def test_business_france_paginates_and_reads_key():
    s = FakeSession(bf_route())
    res = BusinessFranceSource(s).fetch()
    assert len(res.offers) == 120 and res.complete
    posts = [c for c in s.calls if c[0] == "POST"]
    assert [c[2]["json"]["skip"] for c in posts] == [0, 100]


def test_business_france_refreshes_key_on_401():
    s = FakeSession(bf_route(fail_first_with_401=True))
    assert len(BusinessFranceSource(s).fetch().offers) == 120


def test_business_france_fails_safe_on_empty():
    s = FakeSession(lambda m, u, kw: FakeResponse(text=HOME) if m == "GET" else FakeResponse(body={"count": 0, "result": []}))
    with pytest.raises(SourceError):
        BusinessFranceSource(s).fetch()


def test_business_france_http_error():
    s = FakeSession(lambda m, u, kw: FakeResponse(text=HOME) if m == "GET" else FakeResponse(503, text="down"))
    with pytest.raises(SourceError, match="503"):
        BusinessFranceSource(s).fetch()


def test_to_offer_fields():
    o = to_offer(bf_raw(247434, specializations=[{"label": "Finance / Audit"}]))
    assert o.url == "https://mon-vie-via.businessfrance.fr/offres/247434"
    assert o.city == "Singapour" and o.duration == "12 mois" and o.salary == "3 215 €/mois"
    assert o.published == "2026-10-26" and o.deadline == "2026-11-25"
    assert "financière" in o.description and "<b>" not in o.description
    assert "Finance / Audit" in o.tags and o.mission_type == "VIE"


def test_google_alerts_feed():
    xml = (FIXTURES / "google_alerts.xml").read_bytes()
    s = FakeSession(lambda m, u, kw: FakeResponse(text=xml.decode(), content=xml))
    res = RssSource(s, "GA", "https://www.google.com/alerts/feeds/1/2").fetch()
    assert len(res.offers) == 2
    o = res.offers[0]
    assert o.url == "https://www.linkedin.com/jobs/view/123456"
    assert o.title == "V.I.E - Treasury Analyst - Singapore" and o.published == "2026-10-26"
    assert unwrap("https://example.com/x") == "https://example.com/x"


def _page_session(robots="User-agent: *\nAllow: /\n"):
    html = (FIXTURES / "bnp_vie.html").read_text(encoding="utf-8")

    def route(method, url, kw):
        if url.endswith("/robots.txt"):
            return FakeResponse(text=robots)
        if url.endswith("/vie"):
            return FakeResponse(text=html)
        return FakeResponse(text="<html><nav>menu</nav><p>Within Global Markets you will price structured products.</p></html>")
    return FakeSession(route)


def test_page_watch_extracts_offer_links(monkeypatch):
    monkeypatch.setattr(vhttp, "_robots_cache", {})
    src = PageWatchSource(_page_session(), "BNP Paribas – offres V.I.E",
                          "https://group.bnpparibas/emploi-carriere/toutes-offres-emploi/vie",
                          "/emploi-carriere/offre-emploi/", assume_vie=True, fetch_details=True)
    res = src.fetch()
    titles = [o.title for o in res.offers]
    assert len(res.offers) == 3 and res.complete
    assert "V.I.E - Structured Products Sales - Frankfurt, H/F" in titles
    assert all(o.url.startswith("https://group.bnpparibas/emploi-carriere/offre-emploi/") for o in res.offers)
    o = res.offers[0]
    assert src.enrich(o) and "structured products" in o.description and "menu" not in o.description


def test_page_watch_respects_robots(monkeypatch):
    monkeypatch.setattr(vhttp, "_robots_cache", {})
    src = PageWatchSource(_page_session("User-agent: *\nDisallow: /emploi-carriere/\n"), "BNP",
                          "https://group.bnpparibas/emploi-carriere/toutes-offres-emploi/vie", "/offre-emploi/")
    with pytest.raises(SourceError, match="robots"):
        src.fetch()


def test_workday_url_parsing_and_fetch():
    def route(method, url, kw):
        assert url == "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/Careers/jobs"
        return FakeResponse(body={"jobPostings": [{"title": "VIE Treasury Analyst", "externalPath": "/job/Paris/VIE_R1",
                                                   "locationsText": "Paris"}]})
    src = WorkdaySource(FakeSession(route), "ACME", "https://acme.wd3.myworkdayjobs.com/fr-FR/Careers", ["VIE"])
    res = src.fetch()
    assert res.offers[0].url == "https://acme.wd3.myworkdayjobs.com/Careers/job/Paris/VIE_R1"


def test_build_sources_skips_empty_templates_and_reports_bad_config():
    cfg = {"business_france": {"enabled": True},
           "rss": [{"name": "vide", "url": ""}],
           "workday": [{"name": "cassé", "url": "https://example.com/pas-workday"}],
           "page_watch": [{"name": "regex", "url": "https://x.y/z", "link_pattern": "(["}]}
    srcs = build_sources(cfg, FakeSession(lambda *a: FakeResponse()))
    names = [s.name for s in srcs]
    assert names[0] == "Business France" and sorted(names[1:]) == ["cassé", "regex"]
    for s in srcs[1:]:
        with pytest.raises(SourceError, match="configuration invalide"):
            s.fetch()


def test_scrub_hides_secrets(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:SECRET")
    assert "SECRET" not in vhttp.scrub("https://api.telegram.org/bot123:SECRET/sendMessage failed")
    assert vhttp.scrub("https://x/exec?token=abc&y=1") == "https://x/exec?token=***&y=1"
