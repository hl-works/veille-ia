"""Rejeu multi-jours : régénère le digest Telegram (nouveau format détaillé)
pour les N derniers jours et le publie sur le canal — un message par jour.

Utile pour « rattraper » le canal avec le nouveau format sans attendre le cron.
On ne modifie PAS les anciens messages (Telegram ne permet pas d'éditer un
message dont on n'a pas gardé l'identifiant) : on POSTE de nouveaux messages,
datés, du plus ancien au plus récent.

Ce module ne touche NI à feed.json NI à seen.json : il ne fait que republier des
digests Telegram. La collecte historique passe par `advanced_search` (comme le
backfill), avec les mêmes garde-fous de budget.

Usage :
    python -m veille.replay --dry-run                 # aperçu du DERNIER jour (test)
    python -m veille.replay --days 1                  # publie le dernier jour
    python -m veille.replay --days 7                  # publie les 7 derniers jours
    python -m veille.replay --days 5 --dry-run        # aperçu des 5 derniers jours
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

from .config import load_settings
from .digest import build_digest
from .telegram import send_message
from .twitter import advanced_search


# Plafonds par défaut du rejeu (réutilisés par l'écouteur de commandes Telegram).
DEFAULT_MAX_PER_ACCOUNT = 12
DEFAULT_MAX_PER_DAY = 400
DEFAULT_MAX_PAGES = 4


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _day_windows(days: int, *, now: datetime) -> list[tuple[datetime, datetime]]:
    """Renvoie les fenêtres [début, fin) UTC des N derniers jours calendaires,
    du plus ANCIEN au plus RÉCENT. Le dernier jour (aujourd'hui) est borné à
    l'instant présent."""
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    windows: list[tuple[datetime, datetime]] = []
    for offset in range(days - 1, -1, -1):
        start = today_start - timedelta(days=offset)
        end = min(start + timedelta(days=1), now)
        if end > start:
            windows.append((start, end))
    return windows


def run_replay(
    config_path: str,
    *,
    days: int,
    max_per_account: int,
    max_per_day: int,
    max_pages: int,
    dry_run: bool,
    sleep_between: float,
    now: datetime | None = None,
) -> int:
    settings = load_settings(config_path)
    if not settings.accounts:
        logging.error("Aucun compte dans config.yaml. Rien à faire.")
        return 1
    settings.require_secrets()  # Anthropic + twitterapi

    if not dry_run and not settings.telegram_ready:
        logging.error(
            "Telegram non configuré (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID manquants) : "
            "impossible de publier. Relance avec --dry-run pour un aperçu, ou "
            "renseigne les secrets Telegram."
        )
        return 1

    now = now or datetime.now(timezone.utc)
    windows = _day_windows(days, now=now)
    logging.info(
        "Rejeu de %d jour(s) — %s → %s, %d comptes, format « %s ».",
        len(windows), windows[0][0].date(), windows[-1][1].date(),
        len(settings.accounts), settings.digest_depth,
    )

    posted = 0
    for start, end in windows:
        label = start.strftime("%d/%m/%Y")
        logging.info("── Jour %s ──────────────────────────────", label)
        tweets = advanced_search(
            settings.accounts,
            settings.twitterapi_io_key,
            since=start,
            until=end,
            max_per_account=max_per_account,
            max_total=max_per_day,
            max_pages_per_account=max_pages,
            include_retweets=settings.include_retweets,
            include_replies=settings.include_replies,
        )
        if not tweets:
            logging.info("Jour %s : aucun tweet pertinent → on saute.", label)
            continue

        # Digest daté du jour concerné (et non d'aujourd'hui).
        tweets.sort(key=lambda t: t.created_at or start, reverse=True)
        digest = build_digest(tweets, settings, for_date=start)
        message = f"<b>🤖 Veille IA — {label}</b>\n\n{digest}"

        if dry_run:
            print("\n" + "=" * 70)
            print(f"DRY-RUN — digest du {label} qui SERAIT publié ({len(tweets)} tweets) :\n")
            print(message)
            print("=" * 70 + "\n")
            posted += 1
            continue

        try:
            send_message(
                message,
                bot_token=settings.telegram_bot_token,
                chat_id=settings.telegram_chat_id,
            )
            posted += 1
            logging.info("Jour %s publié sur Telegram. ✅", label)
        except Exception as exc:  # noqa: BLE001
            logging.error("Échec de publication du jour %s : %s", label, exc)

        if sleep_between and (start, end) != windows[-1]:
            time.sleep(sleep_between)  # respire entre deux jours (rate limit)

    logging.info("Rejeu terminé : %d jour(s) %s.", posted, "affiché(s)" if dry_run else "publié(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rejeu multi-jours du digest Telegram (nouveau format)."
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--days", type=int, default=1, help="Nombre de derniers jours à rejouer (défaut 1).")
    parser.add_argument("--max-per-account", type=int, default=DEFAULT_MAX_PER_ACCOUNT, help="Quota de tweets par compte et par jour.")
    parser.add_argument("--max-per-day", type=int, default=DEFAULT_MAX_PER_DAY, help="Garde-fou global strict par jour (budget).")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="Pages advanced_search max par compte et par jour.")
    parser.add_argument("--dry-run", action="store_true", help="Affiche les digests sans publier sur Telegram.")
    parser.add_argument("--sleep", type=float, default=3.0, help="Pause (s) entre deux jours publiés.")
    args = parser.parse_args()

    if args.days < 1:
        print("--days doit être >= 1", file=sys.stderr)
        return 2

    _setup_logging()
    try:
        return run_replay(
            args.config,
            days=args.days,
            max_per_account=args.max_per_account,
            max_per_day=args.max_per_day,
            max_pages=args.max_pages,
            dry_run=args.dry_run,
            sleep_between=args.sleep,
        )
    except Exception as exc:  # noqa: BLE001
        logging.error("Échec du rejeu : %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
