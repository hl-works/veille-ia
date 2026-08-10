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
from .sources import collect_extra_sources
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

    # ── Sortie b) feed.json (pour le site) — X UNIQUEMENT ─────────────────
    #  Contrat du site inchangé : le feed ne contient que des sujets issus de X.
    #  En dry-run on n'écrit pas le feed (juste un aperçu du nombre d'entrées).
    if tweets:
        feed_entries = select_and_write_entries(tweets, settings, label="quotidien")
        if dry_run:
            logging.info("[dry-run] %d entrées feed.json seraient ajoutées.", len(feed_entries))
        else:
            append_entries(feed_entries, feed_path=settings.feed_path, seen_path=settings.seen_path)

    # ── Sources complémentaires (Hacker News, RSS) → digest Telegram SEUL ──
    extra = collect_extra_sources(settings, lookback_hours=settings.lookback_hours)
    digest_items = tweets + extra
    digest_items.sort(
        key=lambda t: t.created_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    if extra:
        logging.info("Digest enrichi de %d élément(s) hors X (Hacker News / RSS).", len(extra))

    # ── Sortie a) digest Telegram (optionnel) ─────────────────────────────
    if not settings.telegram_ready:
        logging.info("Telegram non configuré → publication Telegram sautée "
                     "(le feed.json pour le site est quand même produit).")
        return 0

    if not digest_items:
        logging.info("Aucun contenu pertinent sur la fenêtre (X + autres sources).")
        if not settings.send_when_empty:
            logging.info("`send_when_empty` est false → on ne publie rien.")
            return 0
        digest = (
            "Bonjour ☀️ Journée plutôt calme côté IA, rien de majeur à "
            "signaler ces dernières 24 h. Bonne journée !"
        )
    else:
        digest = build_digest(digest_items, settings)

    # En-tête daté ajouté au digest.
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    message = f"<b>🤖 Veille IA — {today}</b>\n\n{digest}"

    if dry_run:
        print("\n" + "=" * 70)
        print("DRY-RUN — digest qui SERAIT publié sur Telegram :\n")
        print(message)
        print("=" * 70 + "\n")
        return 0

    # L'envoi Telegram ne doit JAMAIS bloquer la livraison du feed au site :
    # en cas d'échec (bot pas admin du canal, réseau, 403…), on logue et on
    # continue. Le feed.json a déjà été produit plus haut.
    try:
        send_message(
            message,
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
        logging.info("Veille publiée sur Telegram. ✅")
    except Exception as exc:  # noqa: BLE001
        logging.warning(
            "Publication Telegram échouée (%s) — sans impact sur le feed du site. "
            "Si c'est un 403 « bot is not a member », ajoute le bot comme "
            "administrateur du canal.",
            exc,
        )
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
