from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "config" / "sources.toml"
STATE_DIR = ROOT / "state"


def env(name: str, default: str = "") -> str:
    # strip() : un retour à la ligne collé dans un secret GitHub suffit à tout casser.
    # Un secret GitHub absent arrive comme chaîne vide : on applique alors la valeur par défaut.
    return os.environ.get(name, "").strip() or default


@dataclass
class Secrets:
    telegram_token: str
    telegram_chat_id: str
    smtp_user: str
    smtp_password: str
    smtp_host: str
    smtp_port: int
    email_to: str
    fastlane_url: str
    fastlane_token: str

    @classmethod
    def from_env(cls) -> "Secrets":
        user = env("SMTP_USER")
        return cls(
            telegram_token=env("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=env("TELEGRAM_CHAT_ID"),
            smtp_user=user,
            smtp_password=env("SMTP_PASSWORD"),
            smtp_host=env("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(env("SMTP_PORT", "465") or 465),
            email_to=env("ALERT_EMAIL_TO", user),
            fastlane_url=env("FASTLANE_URL"),
            fastlane_token=env("FASTLANE_TOKEN"),
        )


def load_sources(path: Path = SOURCES_FILE) -> dict:
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    cfg.setdefault("general", {})
    cfg.setdefault("business_france", {"enabled": True})
    return cfg
