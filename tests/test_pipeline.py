"""Tests de bout en bout du passage complet, sans réseau."""
from vie_alert import app
from vie_alert.config import Secrets
from vie_alert.fastlane import FastlaneStatus
from vie_alert.models import Offer
from vie_alert.sources.base import FetchResult, Source, SourceError
from vie_alert.sources.business_france import BusinessFranceSource
from vie_alert.state import State, iso, now_utc

CFG = {"general": {"heartbeat_hour": -1, "max_notifications_per_run": 2, "failure_alert_after": 3},
       "business_france": {"enabled": True, "backup_interval_minutes": 30}}
SECRETS = Secrets("", "", "", "", "", 465, "", "", "")


class ListSource(Source):
    def __init__(self, name, offers, complete=True, require_vie=True):
        super().__init__(None)
        self.name, self.offers, self.complete, self.require_vie = name, offers, complete, require_vie
        self.error = None

    def fetch(self):
        if self.error:
            raise SourceError(self.error)
        return FetchResult(list(self.offers), self.complete)


class FakeBF(BusinessFranceSource):
    def __init__(self, offers):
        Source.__init__(self, None)
        self.offers = offers

    def fetch(self):
        return FetchResult(list(self.offers), True)


class RecNotifier:
    def __init__(self, fail_offers=False):
        self.offers, self.system_msgs, self.summaries = [], [], []
        self.fail_offers = fail_offers
        self.configured = True

    def offer(self, o):
        if self.fail_offers:
            return False
        self.offers.append(o)
        return True

    def system(self, text, subject=""):
        self.system_msgs.append(text)
        return True

    def summary(self, header, offers, subject):
        self.summaries.append((header, list(offers)))
        return True


def offer(uid, title, source="Test", **kw):
    return Offer(source=source, uid=uid, title=title, url=f"https://ex.com/{uid}", **kw)


def run(tmp_path, sources, notifier, state=None, monkeypatch=None, fast=None):
    state = state or State(tmp_path)
    if monkeypatch is not None:
        monkeypatch.setattr(app, "fetch_status", lambda s, sess: fast)
    return app.run(cfg=CFG, secrets=SECRETS, session=None, state=state, notifier=notifier, sources=sources), state


def test_first_run_sends_digest_then_only_new_offers(tmp_path, monkeypatch):
    src = ListSource("Test", [offer("1", "VIE Treasury Analyst"), offer("2", "VIE Data Engineer")])
    n1 = RecNotifier()
    run(tmp_path, [src], n1, monkeypatch=monkeypatch)
    assert n1.offers == [] and len(n1.summaries) == 1
    assert [o.uid for o in n1.summaries[0][1]] == ["1"]          # seule l'offre finance

    src.offers.append(offer("3", "V.I.E - M&A Analyst"))
    src.offers.append(offer("4", "Marketing assistant"))            # pas finance
    src.offers.append(offer("5", "Financial Analyst"))              # finance mais pas V.I.E
    n2 = RecNotifier()
    run(tmp_path, [src], n2, monkeypatch=monkeypatch)
    assert [o.uid for o in n2.offers] == ["3"]
    assert n2.offers[0].domain == "Analyse & investissement"

    n3 = RecNotifier()
    run(tmp_path, [src], n3, monkeypatch=monkeypatch)
    assert n3.offers == [] and n3.summaries == []                   # pas de répétition


def test_failed_notification_is_retried(tmp_path, monkeypatch):
    src = ListSource("Test", [])
    run(tmp_path, [src], RecNotifier(), monkeypatch=monkeypatch)
    src.offers = [offer("9", "VIE Credit Analyst")]
    run(tmp_path, [src], RecNotifier(fail_offers=True), monkeypatch=monkeypatch)
    n = RecNotifier()
    run(tmp_path, [src], n, monkeypatch=monkeypatch)
    assert [o.uid for o in n.offers] == ["9"]


def test_cap_then_summary(tmp_path, monkeypatch):
    src = ListSource("Test", [])
    run(tmp_path, [src], RecNotifier(), monkeypatch=monkeypatch)
    src.offers = [offer(str(i), f"VIE Risk Analyst {i}", published=f"2026-10-{10 + i}") for i in range(5)]
    n = RecNotifier()
    run(tmp_path, [src], n, monkeypatch=monkeypatch)
    assert len(n.offers) == 2 and len(n.summaries) == 1 and len(n.summaries[0][1]) == 3
    assert n.offers[0].uid == "4"                                    # la plus récente d'abord


def test_source_failure_alerts_once_after_threshold_and_recovery(tmp_path, monkeypatch):
    bad = ListSource("Cassée", [])
    good = ListSource("OK", [])
    state = State(tmp_path)
    bad.error = "HTTP 500"
    msgs = []
    for _ in range(4):
        n = RecNotifier()
        run(tmp_path, [bad, good], n, state=state, monkeypatch=monkeypatch)
        msgs += n.system_msgs
    assert len([m for m in msgs if "Source en panne" in m]) == 1
    bad.error = None
    n = RecNotifier()
    run(tmp_path, [bad, good], n, state=state, monkeypatch=monkeypatch)
    assert any("rétablie" in m for m in n.system_msgs)


def test_via_excluded_and_fastlane_dedupe(tmp_path, monkeypatch):
    bf = FakeBF([])
    run(tmp_path, [bf], RecNotifier(), monkeypatch=monkeypatch)
    bf.offers = [offer("10", "VIE Treasury Analyst", source="Business France", mission_type="VIE", vie_certain=True),
                 offer("11", "Chargé de mission financier", source="Business France", mission_type="VIA", vie_certain=True),
                 offer("12", "VIE Controller", source="Business France", mission_type="VIE", vie_certain=True)]
    fast = FastlaneStatus(reachable=True, last_bf_scan=now_utc(), bf_ok=True, sent_ids={"12"})
    state = State(tmp_path)
    state.status["bf_last_scan"] = "2000-01-01T00:00:00Z"            # scan de secours dû
    n = RecNotifier()
    run(tmp_path, [bf], n, state=state, monkeypatch=monkeypatch, fast=fast)
    assert [o.uid for o in n.offers] == ["10"]                       # 11 = V.I.A, 12 = déjà envoyée


def test_bf_skipped_when_fastlane_healthy(tmp_path, monkeypatch):
    bf = FakeBF([offer("1", "VIE Treasury Analyst", source="Business France", vie_certain=True)])
    state = State(tmp_path)
    state.status["bf_last_scan"] = iso(now_utc())
    fast = FastlaneStatus(reachable=True, last_bf_scan=now_utc(), bf_ok=True)
    run(tmp_path, [bf], RecNotifier(), state=state, monkeypatch=monkeypatch, fast=fast)
    assert not state.initialized("Business France")                  # pas scanné : la voie rapide s'en charge


def test_fastlane_down_alert(tmp_path, monkeypatch):
    fast = FastlaneStatus(reachable=False, error="timeout")
    n = RecNotifier()
    _, state = run(tmp_path, [], n, monkeypatch=monkeypatch, fast=fast)
    assert any("Voie rapide" in m for m in n.system_msgs)
    n2 = RecNotifier()
    run(tmp_path, [], n2, state=state, monkeypatch=monkeypatch, fast=fast)
    assert n2.system_msgs == []                                      # pas de répétition


def test_state_persisted(tmp_path, monkeypatch):
    src = ListSource("Test", [offer("1", "VIE Treasury Analyst")])
    run(tmp_path, [src], RecNotifier(), monkeypatch=monkeypatch)
    assert (tmp_path / "seen.json").exists() and (tmp_path / "status.json").exists()
    assert State(tmp_path).is_seen("Test", "1")
