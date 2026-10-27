"""Orchestration : un passage = toutes les sources -> filtre -> notifications -> état."""
from __future__ import annotations

import html
import logging
from datetime import timedelta

import requests

from .classify import Classifier
from .config import Secrets, load_sources
from .fastlane import FastlaneStatus, fetch_status
from .http import make_session, scrub
from .models import Offer
from .notify import Notifier
from .sources import BusinessFranceSource, Source, build_sources
from .state import PARIS, State, iso, now_utc, parse_iso

log = logging.getLogger(__name__)


def evaluate(o: Offer, src: Source, clf: Classifier, include_via: bool) -> bool:
    """True si l'offre est un V.I.E en finance (et renseigne o.domain / o.basis)."""
    if "VIA" in o.mission_type and "VIE" not in o.mission_type and not include_via:
        return False
    if src.require_vie and not o.vie_certain and not clf.looks_vie(o.title, o.description, o.tags):
        return False
    v = clf.classify(o.title, o.description, o.tags)
    if src.require_finance and not v.is_finance:
        return False
    o.domain, o.basis = (v.domain, v.basis) if v.is_finance else ("Non classé (alerte)", "")
    return True


def _bf_backup_due(state: State, minutes: int) -> bool:
    last = parse_iso(state.status.get("bf_last_scan"))
    return last is None or now_utc() - last >= timedelta(minutes=minutes - 1)


def _handle_failure(src: Source, err: Exception, state: State, notifier: Notifier, alert_after: int) -> None:
    msg = scrub(str(err)) or err.__class__.__name__
    st = state.record_fail(src.name, msg)
    state.daily()["errors"] += 1
    log.warning("Source en échec : %s (%s) [%d fois de suite]", src.name, msg, st["consecutive_failures"])
    if st["consecutive_failures"] >= alert_after and not st.get("alerted"):
        if notifier.system(f"⚠️ <b>Source en panne</b> depuis {st['consecutive_failures']} passages : "
                           f"{html.escape(src.name)}\n<code>{html.escape(msg[:300])}</code>\n"
                           f"Les autres sources continuent de tourner."):
            st["alerted"] = True


def _fastlane_watchdog(fast: FastlaneStatus | None, healthy: bool, state: State, notifier: Notifier) -> None:
    if fast is None:
        return
    alerted = state.status.get("fastlane_alerted", False)
    if not healthy and not alerted:
        if notifier.system("⚠️ <b>Voie rapide (Apps Script) en panne</b> : " + html.escape(fast.describe())
                           + "\nLe script GitHub reprend le scan Business France à chaque passage en attendant."):
            state.status["fastlane_alerted"] = True
    elif healthy and alerted:
        notifier.system("✅ Voie rapide (Apps Script) rétablie.")
        state.status["fastlane_alerted"] = False


def _heartbeat(cfg: dict, state: State, notifier: Notifier, sources: list[Source],
               fast: FastlaneStatus | None, force: bool = False) -> None:
    hour = int(cfg["general"].get("heartbeat_hour", 20))
    now = now_utc().astimezone(PARIS)
    today = now.strftime("%Y-%m-%d")
    if not force and (hour < 0 or now.hour < hour or state.status.get("last_heartbeat") == today):
        return
    d = state.daily()
    lines = ["📊 <b>Bilan du jour – veille V.I.E finance</b>",
             f"Passages GitHub : {d['runs']} · nouvelles offres finance : {d['new_finance']} · "
             f"messages envoyés : {d['notified']} · erreurs : {d['errors']}"]
    for src in sources:
        st = state.status["sources"].get(src.name, {})
        if st.get("ok"):
            lines.append(f"✅ {html.escape(src.name)} ({st.get('last_count', 0)} éléments)")
        elif st:
            lines.append(f"❌ {html.escape(src.name)} : {html.escape(st.get('last_error', '')[:120])}")
    if fast is not None:
        lines.append("⚡ Voie rapide : " + html.escape(fast.describe()))
    lines.append("Pas de bilan un soir = quelque chose cloche (onglet Actions sur GitHub).")
    if notifier.system("\n".join(lines)):
        state.status["last_heartbeat"] = today


def run(dry_run: bool = False, only: str | None = None, session: requests.Session | None = None,
        state: State | None = None, notifier: Notifier | None = None, cfg: dict | None = None,
        secrets: Secrets | None = None, clf: Classifier | None = None, sources: list[Source] | None = None) -> int:
    cfg = cfg or load_sources()
    gen = cfg["general"]
    secrets = secrets or Secrets.from_env()
    session = session or make_session()
    clf = clf or Classifier.from_file()
    state = state or State()
    notifier = notifier or Notifier(secrets, dry_run=dry_run)
    if not notifier.configured:
        log.error("Aucun canal de notification : définis TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (ou SMTP_*).")
        return 2

    daily = state.daily()
    daily["runs"] += 1
    include_via = bool(gen.get("include_via", False))
    alert_after = int(gen.get("failure_alert_after", 3))
    fast = fetch_status(secrets, session)
    fast_ok = bool(fast and fast.healthy(int(gen.get("fastlane_stale_minutes", 20))))
    sources = sources if sources is not None else build_sources(cfg, session)

    pending: list[tuple[str, Offer]] = []
    bootstraps: list[tuple[str, list[Offer]]] = []
    for src in sources:
        if only and src.name != only:
            continue
        is_bf = isinstance(src, BusinessFranceSource)
        if is_bf and fast_ok and not _bf_backup_due(state, int(cfg["business_france"].get("backup_interval_minutes", 30))):
            log.info("Business France : voie rapide active, scan de secours pas encore dû")
            continue
        try:
            res = src.fetch()
        except Exception as e:  # une source qui casse ne doit jamais arrêter les autres
            _handle_failure(src, e, state, notifier, alert_after)
            continue
        st = state.record_ok(src.name, len(res.offers))
        if st.pop("recovered", False):
            notifier.system(f"✅ Source rétablie : {html.escape(src.name)}")
        if is_bf:
            state.status["bf_last_scan"] = iso(now_utc())

        first = not state.initialized(src.name)
        relevant = []
        for o in res.offers:
            if state.is_seen(src.name, o.uid):
                continue
            complete_info = True if first else src.enrich(o) is not False
            if evaluate(o, src, clf, include_via):
                relevant.append(o)
            elif complete_info:
                state.mark(src.name, o.uid)
        log.info("%s : %d éléments, %d nouveaux pertinents%s", src.name, len(res.offers), len(relevant),
                 " (initialisation)" if first else "")

        if first:
            state.seen.setdefault(src.name, {})
            for o in res.offers:
                state.mark(src.name, o.uid)
            if relevant:
                bootstraps.append((src.name, relevant))
        else:
            for o in relevant:
                if is_bf and fast and o.uid in fast.sent_ids:
                    state.mark(src.name, o.uid)   # déjà envoyée par la voie rapide
                else:
                    pending.append((src.name, o))
        state.prune(src.name, {o.uid for o in res.offers} if res.complete else None)

    # -- envoi ---------------------------------------------------------------
    daily["new_finance"] += len(pending)
    pending.sort(key=lambda p: p[1].published, reverse=True)
    cap = int(gen.get("max_notifications_per_run", 30))
    for name, o in pending[:cap]:
        if notifier.offer(o):
            state.mark(name, o.uid)
            daily["notified"] += 1
    rest = pending[cap:]
    if rest and notifier.summary(f"➕ <b>{len(rest)} autres nouvelles offres V.I.E finance</b>",
                                 [o for _, o in rest], "[V.I.E finance] Autres nouvelles offres"):
        for name, o in rest:
            state.mark(name, o.uid)
        daily["notified"] += len(rest)
    for name, offers in bootstraps:
        notifier.summary(f"🚀 <b>Initialisation – {html.escape(name)}</b> : {len(offers)} offres V.I.E finance "
                         f"actuellement en ligne (les prochaines arriveront une par une)", offers,
                         f"[V.I.E finance] Offres en ligne – {name}")

    _fastlane_watchdog(fast, fast_ok, state, notifier)
    _heartbeat(cfg, state, notifier, sources, fast)
    state.status["last_run"] = iso(now_utc())
    if not dry_run:
        state.save()
    return 0
