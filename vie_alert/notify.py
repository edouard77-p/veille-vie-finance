"""Notifications : Telegram (principal) et e-mail (secours)."""
from __future__ import annotations

import html
import logging
import re
import smtplib
import time
from email.message import EmailMessage

import requests

from .config import Secrets
from .http import scrub
from .models import Offer

log = logging.getLogger(__name__)
TELEGRAM_LIMIT = 4096
CHUNK = 3800


def fr_date(iso: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else iso


def format_offer(o: Offer) -> str:
    e = html.escape
    lines = [f"🔔 <b>{e(o.title)}</b>"]
    if o.company:
        lines.append(f"🏢 {e(o.company)}")
    if o.location:
        lines.append(f"📍 {e(o.location)}")
    domain = e(o.domain or "Finance")
    if o.basis == "description":
        domain += " · <i>à vérifier (repérée via la description)</i>"
    lines.append(f"💼 {domain}")
    facts = []
    if o.published:
        facts.append(f"publiée le {fr_date(o.published)}")
    if o.start_date:
        facts.append(f"début {fr_date(o.start_date)}")
    for f in (o.duration, o.salary):
        if f:
            facts.append(f)
    if o.deadline:
        facts.append(f"candidature jusqu'au {fr_date(o.deadline)}")
    if facts:
        lines.append("🗓 " + e(" · ".join(facts)))
    if o.description:
        lines.append(f"📝 <i>{e(o.short_description())}</i>")
    lines.append(f"🔗 {e(o.url)}")
    lines.append(f"🛰 Source : {e(o.source)}")
    return "\n".join(lines)


def format_line(o: Offer) -> str:
    """Ligne compacte pour les récapitulatifs."""
    e = html.escape
    where = f" ({e(o.location)})" if o.location else ""
    company = f" — {e(o.company)}" if o.company else ""
    return f"• <a href=\"{e(o.url, quote=True)}\">{e(o.title)}</a>{company}{where} · <i>{e(o.domain)}</i>"


def chunk_lines(header: str, lines: list[str], size: int = CHUNK) -> list[str]:
    chunks, cur = [], header
    for line in lines:
        if len(cur) + len(line) + 1 > size:
            chunks.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)
    return chunks


def to_plain(text: str) -> str:
    text = re.sub(r'<a href="([^"]+)">([^<]*)</a>', r"\2 (\1)", text)
    return html.unescape(re.sub(r"<[^>]+>", "", text))


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id
        self.http = requests.Session()   # sans retry automatique : on gère 429 nous-mêmes
        self._last = 0.0

    def send(self, text: str, button_url: str | None = None) -> bool:
        payload = {"chat_id": self.chat_id, "text": text[:TELEGRAM_LIMIT], "parse_mode": "HTML",
                   "disable_web_page_preview": True}
        if button_url and button_url.startswith("http"):
            payload["reply_markup"] = {"inline_keyboard": [[{"text": "📨 Ouvrir l'offre", "url": button_url}]]}
        for attempt in range(5):
            wait = 1.05 - (time.monotonic() - self._last)   # ~1 message/s par conversation
            if wait > 0:
                time.sleep(wait)
            try:
                r = self.http.post(self.url, json=payload, timeout=20)
            except requests.RequestException as e:
                log.warning("Telegram injoignable (%s), nouvel essai", scrub(str(e)))
                time.sleep(2 ** attempt)
                continue
            finally:
                self._last = time.monotonic()
            if r.ok:
                return True
            try:
                body = r.json()
            except ValueError:
                body = {}
            desc = str(body.get("description", r.text[:200]))
            if r.status_code == 429:
                time.sleep(min(int((body.get("parameters") or {}).get("retry_after", 5)), 60) + 0.5)
                continue
            if r.status_code == 400 and "parse" in desc.lower():
                payload["text"] = to_plain(payload["text"])
                payload.pop("parse_mode", None)
                continue
            if r.status_code == 400 and "reply_markup" in payload and ("button" in desc.lower() or "url" in desc.lower()):
                payload.pop("reply_markup")
                continue
            if r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            log.error("Telegram a refusé le message : HTTP %s %s", r.status_code, scrub(desc))
            return False
        return False


class Email:
    def __init__(self, s: Secrets):
        self.s = s

    def send(self, subject: str, text: str) -> bool:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, self.s.smtp_user, self.s.email_to
        msg.set_content(to_plain(text))
        try:
            with smtplib.SMTP_SSL(self.s.smtp_host, self.s.smtp_port, timeout=30) as smtp:
                smtp.login(self.s.smtp_user, self.s.smtp_password)
                smtp.send_message(msg)
            return True
        except (smtplib.SMTPException, OSError) as e:
            log.error("E-mail non envoyé : %s", scrub(str(e)))
            return False


class Notifier:
    def __init__(self, secrets: Secrets, dry_run: bool = False):
        self.dry_run = dry_run
        self.telegram = Telegram(secrets.telegram_token, secrets.telegram_chat_id) \
            if secrets.telegram_token and secrets.telegram_chat_id else None
        self.email = Email(secrets) if secrets.smtp_user and secrets.smtp_password and secrets.email_to else None
        self.sent = 0

    @property
    def configured(self) -> bool:
        return self.dry_run or bool(self.telegram or self.email)

    def _send(self, text: str, subject: str, button_url: str | None = None) -> bool:
        if self.dry_run:
            print("\n" + to_plain(text) + "\n" + "-" * 60)
            return True
        if self.telegram and self.telegram.send(text, button_url):
            self.sent += 1
            return True
        if self.email and self.email.send(subject, text):
            self.sent += 1
            return True
        return False

    def offer(self, o: Offer) -> bool:
        return self._send(format_offer(o), f"[V.I.E finance] {o.title} – {o.company}", o.url)

    def system(self, text: str, subject: str = "[V.I.E finance] Message du système") -> bool:
        return self._send(text, subject)

    def summary(self, header: str, offers: list[Offer], subject: str) -> bool:
        ok = True
        for part in chunk_lines(header, [format_line(o) for o in offers]):
            ok = self._send(part, subject) and ok
        return ok
