"""Point d'entrée du bot de veille IA.

Pipeline : récupère les tweets récents → Claude rédige le digest → publie
sur Telegram.

Usage :
    python -m veille.main                 # exécution normale (publie sur Telegram)
    python -m veille.main --dry-run       # affiche le digest sans publier
    python -m veille.main --config x.yaml # autre fichier de config
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from .config import load_settings
from .digest import build_digest
from .feed import append_entries, select_and_write_entries
from .telegram import send_message
from .twitter import collect_recent_tweets


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def run(config_path: str, *, dry_run: bool) -> int:
    settings = load_settings(config_path)

    if not settings.accounts:
        logging.error("Aucun compte dans config.yaml (champ `accounts`). Rien à faire.")
        return 1

    # Secrets indispensables : la collecte + la rédaction (Anthropic, twitterapi).
    # Telegram est optionnel : s'il n'est pas configuré, on alimente quand même
    # le site et on saute simplement la publication Telegram.
    settings.require_secrets()

    tweets = collect_recent_tweets(
        settings.accounts,
        settings.twitterapi_io_key,
        lookback_hours=settings.lookback_hours,
        max_per_account=settings.max_tweets_per_account,
        include_retweets=settings.include_retweets,
        include_replies=settings.include_replies,
    )

    # ── Sortie b) feed.json (pour le site) — à partir de la même collecte ──
    #  En dry-run on n'écrit pas le feed (juste un aperçu du nombre d'entrées).
    if tweets:
        feed_entries = select_and_write_entries(tweets, settings, label="quotidien")
        if dry_run:
            logging.info("[dry-run] %d entrées feed.json seraient ajoutées.", len(feed_entries))
        else:
            append_entries(feed_entries, feed_path=settings.feed_path, seen_path=settings.seen_path)

    # ── Sortie a) digest Telegram (optionnel) ─────────────────────────────
    if not settings.telegram_ready:
        logging.info("Telegram non configuré → publication Telegram sautée "
                     "(le feed.json pour le site est quand même produit).")
        return 0

    if not tweets:
        logging.info("Aucun tweet pertinent sur la fenêtre.")
        if not settings.send_when_empty:
            logging.info("`send_when_empty` est false → on ne publie rien.")
            return 0
        digest = (
            "Bonjour ☀️ Journée plutôt calme côté IA, rien de majeur à "
            "signaler ces dernières 24 h. Bonne journée !"
        )
    else:
        digest = build_digest(tweets, settings)

    # En-tête daté ajouté au digest.
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    message = f"<b>🤖 Veille IA — {today}</b>\n\n{digest}"

    if dry_run:
        print("\n" + "=" * 70)
        print("DRY-RUN — digest qui SERAIT publié sur Telegram :\n")
        print(message)
        print("=" * 70 + "\n")
        return 0

    send_message(
        message,
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )
    logging.info("Veille publiée avec succès. ✅")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bot de veille IA (Twitter → Claude → Telegram).")
    parser.add_argument("--config", default="config.yaml", help="Chemin du fichier de config.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche le digest sans publier sur Telegram.",
    )
    args = parser.parse_args()

    _setup_logging()
    try:
        return run(args.config, dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 — on veut un message clair en CI
        logging.error("Échec de la veille : %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
