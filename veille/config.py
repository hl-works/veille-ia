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
    # Profondeur du digest Telegram : « detaille » (développé, lecture hors ligne)
    # ou « essentiel » (survol court à l'ancienne).
    digest_depth: str = "detaille"
    # Sources complémentaires (en plus de X) — alimentent le digest Telegram
    # uniquement, jamais feed.json.
    include_hackernews: bool = False
    hackernews_min_score: int = 60
    include_rss: bool = False
    rss_feeds: list[str] = field(default_factory=list)
    include_youtube: bool = False
    youtube_channels: list[str] = field(default_factory=list)
    youtube_ai_filter: bool = False
    feed_path: str = "feed.json"
    seen_path: str = "seen.json"

    # Secrets (depuis l'environnement / GitHub Secrets)
    anthropic_api_key: str = ""
    twitterapi_io_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @property
    def telegram_ready(self) -> bool:
        """Telegram est utilisable seulement si ses deux secrets sont présents.
        Sinon on saute la publication Telegram sans planter."""
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    def require_secrets(self, need_telegram: bool = False) -> None:
        """Vérifie les secrets INDISPENSABLES (collecte + rédaction). Telegram
        est optionnel et géré séparément via `telegram_ready` ; le paramètre
        `need_telegram` est accepté (compat backfill) mais Telegram n'est jamais
        bloquant ici."""
        missing: list[str] = []
        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        if not self.twitterapi_io_key:
            missing.append("TWITTERAPI_IO_KEY")
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
    # Nettoyage : retire les @ et les espaces éventuels, et dédoublonne en
    # gardant l'ordre (un doublon = un compte facturé deux fois pour rien).
    cleaned = [str(a).strip().lstrip("@") for a in accounts if str(a).strip()]
    accounts = list(dict.fromkeys(cleaned))

    # Profondeur du digest : on tolère quelques variantes d'écriture.
    depth = str(raw.get("digest_depth", "detaille")).strip().lower()
    depth = "essentiel" if depth in {"essentiel", "court", "concis"} else "detaille"

    # Sources complémentaires (bloc `sources:` optionnel + listes dédiées).
    src = raw.get("sources") or {}
    rss_feeds = [str(u).strip() for u in (raw.get("rss_feeds") or []) if str(u).strip()]
    youtube_channels = [str(c).strip() for c in (raw.get("youtube_channels") or []) if str(c).strip()]

    return Settings(
        accounts=accounts,
        lookback_hours=int(raw.get("lookback_hours", 24)),
        max_tweets_per_account=int(raw.get("max_tweets_per_account", 20)),
        include_retweets=bool(raw.get("include_retweets", False)),
        include_replies=bool(raw.get("include_replies", False)),
        model=str(raw.get("model", "claude-opus-4-8")),
        language=str(raw.get("language", "français")),
        send_when_empty=bool(raw.get("send_when_empty", False)),
        digest_depth=depth,
        include_hackernews=bool(src.get("hacker_news", False)),
        hackernews_min_score=int(src.get("hacker_news_min_score", 60)),
        include_rss=bool(src.get("rss", False)),
        rss_feeds=rss_feeds,
        include_youtube=bool(src.get("youtube", False)),
        youtube_channels=youtube_channels,
        youtube_ai_filter=bool(src.get("youtube_ai_filter", False)),
        feed_path=str(raw.get("feed_path", "feed.json")),
        seen_path=str(raw.get("seen_path", "seen.json")),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        twitterapi_io_key=os.environ.get("TWITTERAPI_IO_KEY", ""),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        # Accepte les deux noms (TELEGRAM_CHAT_ID historique + TELEGRAM_CHANNEL_ID).
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID")
        or os.environ.get("TELEGRAM_CHANNEL_ID", ""),
    )
