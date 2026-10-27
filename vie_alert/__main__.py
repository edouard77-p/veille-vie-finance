"""Ligne de commande.

  python -m vie_alert run          un passage complet (utilisé par GitHub Actions)
  python -m vie_alert check        teste chaque source et la voie rapide, sans rien marquer comme vu
  python -m vie_alert test-notify  envoie une fausse offre + un message système (test des alertes)
  python -m vie_alert digest       envoie la liste de TOUTES les offres V.I.E finance en ligne
  python -m vie_alert heartbeat    envoie le bilan du jour tout de suite
  python -m vie_alert chat-id      affiche l'identifiant de ta conversation Telegram
  python -m vie_alert explain "Titre" [--desc "texte"]   explique la décision du filtre finance
Option commune : --dry-run (affiche au lieu d'envoyer, n'écrit pas l'état).
"""
from __future__ import annotations

import argparse
import html
import logging
import sys

import requests

from . import app
from .classify import Classifier
from .config import Secrets, load_sources
from .fastlane import fetch_status
from .http import make_session, scrub
from .models import Offer
from .notify import Notifier
from .sources import build_sources
from .state import State


def cmd_check(args) -> int:
    cfg, secrets, session = load_sources(), Secrets.from_env(), make_session()
    clf, notifier = Classifier.from_file(), Notifier(Secrets.from_env(), dry_run=args.dry_run)
    include_via = bool(cfg["general"].get("include_via", False))
    lines, failures = ["🩺 <b>Diagnostic des sources</b>"], 0
    for src in build_sources(cfg, session):
        try:
            res = src.fetch()
            relevant = [o for o in res.offers if app.evaluate(o, src, clf, include_via)]
            lines.append(f"✅ {html.escape(src.name)} : {len(res.offers)} éléments, {len(relevant)} V.I.E finance")
            for o in relevant[:3]:
                lines.append(f"   ↳ {html.escape(o.title[:80])} · {html.escape(o.domain)}")
        except Exception as e:
            failures += 1
            lines.append(f"❌ {html.escape(src.name)} : {html.escape(scrub(str(e))[:200])}")
    fast = fetch_status(secrets, session)
    lines.append("⚡ Voie rapide : " + ("non configurée (FASTLANE_URL vide)" if fast is None
                                        else html.escape(fast.describe())))
    lines.append("📨 Telegram : " + ("configuré" if notifier.telegram else "NON configuré")
                 + " · e-mail de secours : " + ("configuré" if notifier.email else "non configuré"))
    text = "\n".join(lines)
    print(html.unescape(text.replace("<b>", "").replace("</b>", "")))
    if notifier.configured and not args.dry_run:
        notifier.system(text, "[V.I.E finance] Diagnostic")
    return 1 if failures else 0


def cmd_test_notify(args) -> int:
    notifier = Notifier(Secrets.from_env(), dry_run=args.dry_run)
    if not notifier.configured:
        print("Aucun canal configuré (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID ou SMTP_*)")
        return 2
    sample = Offer(source="Test", uid="test", title="[TEST] V.I.E – Treasury Analyst (H/F)",
                   url="https://mon-vie-via.businessfrance.fr/offres/recherche", company="Entreprise Exemple",
                   city="Singapour", country="Singapour", published="2026-10-26", start_date="2027-01-01",
                   duration="12 mois", salary="3 200 €/mois", domain="Finance d'entreprise", basis="titre",
                   description="Ceci est un message de test : si tu le lis sur ton téléphone, les alertes fonctionnent.")
    ok_offer = notifier.offer(sample)
    ok_sys = notifier.system("🧪 Message système de test : le canal d'alerte fonctionne.")
    print("Offre de test :", "OK" if ok_offer else "ÉCHEC", "| Message système :", "OK" if ok_sys else "ÉCHEC")
    return 0 if ok_offer and ok_sys else 1


def cmd_digest(args) -> int:
    cfg, session = load_sources(), make_session()
    clf, notifier = Classifier.from_file(), Notifier(Secrets.from_env(), dry_run=args.dry_run)
    include_via = bool(cfg["general"].get("include_via", False))
    for src in build_sources(cfg, session):
        if args.source and src.name != args.source:
            continue
        try:
            offers = [o for o in src.fetch().offers if app.evaluate(o, src, clf, include_via)]
        except Exception as e:
            print(f"{src.name} : échec ({scrub(str(e))})")
            continue
        if offers:
            offers.sort(key=lambda o: (o.domain, o.country))
            notifier.summary(f"📋 <b>{html.escape(src.name)}</b> : {len(offers)} offres V.I.E finance en ligne",
                             offers, f"[V.I.E finance] Récapitulatif {src.name}")
    return 0


def cmd_heartbeat(args) -> int:
    cfg, secrets, session = load_sources(), Secrets.from_env(), make_session()
    notifier = Notifier(secrets, dry_run=args.dry_run)
    state = State()
    app._heartbeat(cfg, state, notifier, build_sources(cfg, session), fetch_status(secrets, session), force=True)
    return 0


def cmd_chat_id(args) -> int:
    token = Secrets.from_env().telegram_token
    if not token:
        print("Définis d'abord TELEGRAM_BOT_TOKEN.")
        return 2
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20).json()
    chats = {(u.get("message") or u.get("channel_post") or {}).get("chat", {}).get("id"):
             (u.get("message") or u.get("channel_post") or {}).get("chat", {}) for u in r.get("result", [])}
    chats.pop(None, None)
    if not chats:
        print("Aucun message reçu : envoie /start à ton bot dans Telegram puis relance.")
        return 1
    for cid, chat in chats.items():
        print(f"TELEGRAM_CHAT_ID = {cid}   ({chat.get('first_name') or chat.get('title', '')})")
    return 0


def cmd_explain(args) -> int:
    clf = Classifier.from_file()
    v = clf.classify(args.title, args.desc or "")
    print(f"Finance : {'OUI' if v.is_finance else 'NON'} | domaine : {v.domain or '-'} | base : {v.basis or '-'}")
    print(f"Termes : {', '.join(v.hits) or '-'} {('| ' + v.reason) if v.reason else ''}")
    print(f"Mention V.I.E détectée : {'oui' if clf.looks_vie(args.title, args.desc or '') else 'non'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    p = argparse.ArgumentParser(prog="vie_alert", description="Veille V.I.E finance")
    p.add_argument("command", choices=["run", "check", "test-notify", "digest", "heartbeat", "chat-id", "explain"],
                   nargs="?", default="run")
    p.add_argument("title", nargs="?", help="(explain) titre d'offre à tester")
    p.add_argument("--desc", help="(explain) description à tester")
    p.add_argument("--source", help="limiter à une source (nom exact)")
    p.add_argument("--dry-run", action="store_true", help="afficher au lieu d'envoyer, sans écrire l'état")
    args = p.parse_args(argv)
    commands = {"run": lambda a: app.run(dry_run=a.dry_run, only=a.source), "check": cmd_check,
                "test-notify": cmd_test_notify, "digest": cmd_digest, "heartbeat": cmd_heartbeat,
                "chat-id": cmd_chat_id, "explain": cmd_explain}
    try:
        return commands[args.command](args)
    except Exception as e:  # dernier filet : message lisible, sans secret, code d'erreur pour GitHub
        logging.exception("Erreur inattendue : %s", scrub(str(e)))
        return 1


if __name__ == "__main__":
    sys.exit(main())
