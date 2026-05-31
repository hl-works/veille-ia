"""Chargement de la configuration : `config.yaml` pour les réglages,
variables d'environnement pour les secrets (clés API, tokens)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Settings:
    """Tous les réglages du bot, regroupés en un seul objet."""

    # Réglages (depuis config.yaml)
    accounts: list[str] = field(default_factory=list)
    lookback_hours: int = 24
    max_tweets_per_account: int = 20
    include_retweets: bool = False
    include_replies: bool = False
    model: str = "claude-opus-4-8"
    language: str = "français"
    send_when_empty: bool = False
    feed_path: str = "feed.json"
    seen_path: str = "seen.json"

    # Secrets (depuis l'environnement / GitHub Secrets)
    anthropic_api_key: str = ""
    twitterapi_io_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    def require_secrets(self, *, need_telegram: bool = True) -> None:
        """Vérifie que les secrets nécessaires sont présents, sinon lève une
        erreur claire indiquant lesquels manquent."""
        missing: list[str] = []
        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        if not self.twitterapi_io_key:
            missing.append("TWITTERAPI_IO_KEY")
        if need_telegram:
            if not self.telegram_bot_token:
                missing.append("TELEGRAM_BOT_TOKEN")
            if not self.telegram_chat_id:
                missing.append("TELEGRAM_CHAT_ID")
        if missing:
            raise RuntimeError(
                "Secrets manquants : "
                + ", ".join(missing)
                + ".\nEn local : copie .env.example en .env et remplis-le, "
                "puis `export $(grep -v '^#' .env | xargs)`.\n"
                "Sur GitHub : ajoute-les dans Settings → Secrets and variables → Actions."
            )


def load_settings(config_path: str | Path = "config.yaml") -> Settings:
    """Lit `config.yaml` + l'environnement et renvoie un objet `Settings`."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Fichier de config introuvable : {path.resolve()}\n"
            "Lance le bot depuis la racine du dépôt, ou passe --config <chemin>."
        )

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    accounts = raw.get("accounts") or []
    # Nettoyage : retire les @ et les espaces éventuels
    accounts = [str(a).strip().lstrip("@") for a in accounts if str(a).strip()]

    return Settings(
        accounts=accounts,
        lookback_hours=int(raw.get("lookback_hours", 24)),
        max_tweets_per_account=int(raw.get("max_tweets_per_account", 20)),
        include_retweets=bool(raw.get("include_retweets", False)),
        include_replies=bool(raw.get("include_replies", False)),
        model=str(raw.get("model", "claude-opus-4-8")),
        language=str(raw.get("language", "français")),
        send_when_empty=bool(raw.get("send_when_empty", False)),
        feed_path=str(raw.get("feed_path", "feed.json")),
        seen_path=str(raw.get("seen_path", "seen.json")),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        twitterapi_io_key=os.environ.get("TWITTERAPI_IO_KEY", ""),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
    )
