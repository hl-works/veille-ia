"""Backfill one-shot : génère le feed.json initial couvrant une période passée
(par défaut mai 2026), pour le contenu de lancement du site.

⚠️ Consomme du budget twitterapi.io (advanced_search). Garde-fous :
- plafond strict de tweets (`--max-tweets`, défaut 600),
- pas de boucle infinie (pagination bornée),
- traitement par lots pour éviter un prompt géant.

Usage :
    python -m veille.backfill                    # mai 2026, dry-run (n'écrit rien)
    python -m veille.backfill --write            # écrit feed.json + seen.json
    python -m veille.backfill --since 2026-05-01 --until 2026-06-01 --write
    python -m veille.backfill --max-tweets 400 --write
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from .config import load_settings
from .feed import append_entries, select_and_write_entries
from .twitter import advanced_search


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _parse_day(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def run_backfill(
    config_path: str,
    *,
    since: datetime,
    until: datetime,
    max_per_account: int,
    max_tweets: int,
    batch_size: int,
    write: bool,
    feed_path: str,
    seen_path: str,
) -> int:
    settings = load_settings(config_path)
    settings.require_secrets(need_telegram=False)  # le backfill ne touche pas Telegram

    logging.info(
        "Backfill %s → %s, %d/compte, plafond global %d, %d comptes.",
        since.date(), until.date(), max_per_account, max_tweets, len(settings.accounts),
    )

    tweets = advanced_search(
        settings.accounts,
        settings.twitterapi_io_key,
        since=since,
        until=until,
        max_per_account=max_per_account,
        max_total=max_tweets,
        include_retweets=settings.include_retweets,
        include_replies=settings.include_replies,
    )
    if not tweets:
        logging.warning("Aucun tweet récupéré sur la période. Rien à faire.")
        return 0

    # On découpe en lots pour ne pas envoyer un prompt démesuré à Claude.
    total_added = 0
    all_entries: list[dict] = []
    for start in range(0, len(tweets), batch_size):
        batch = tweets[start : start + batch_size]
        entries = select_and_write_entries(batch, settings, label=f"backfill {start//batch_size + 1}")
        all_entries.extend(entries)

    logging.info("Backfill : %d entrées sélectionnées au total.", len(all_entries))

    if not write:
        # Aperçu sans écrire.
        import json

        print("\n" + "=" * 70)
        print(f"DRY-RUN backfill — {len(all_entries)} entrées qui SERAIENT écrites :\n")
        preview = [{k: v for k, v in e.items() if k != "_tweet_id"} for e in all_entries[:10]]
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        if len(all_entries) > 10:
            print(f"\n… (+{len(all_entries) - 10} autres)")
        print("=" * 70 + "\n")
        print("Relance avec --write pour générer feed.json + seen.json.")
        return 0

    total_added = append_entries(all_entries, feed_path=feed_path, seen_path=seen_path)
    logging.info("Backfill terminé : %d entrées ajoutées à %s.", total_added, feed_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill feed.json (one-shot, borné).")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--since", default="2026-05-01", help="Date de début (YYYY-MM-DD, incluse).")
    parser.add_argument("--until", default="2026-06-01", help="Date de fin (YYYY-MM-DD, exclue).")
    parser.add_argument("--max-per-account", type=int, default=25, help="Quota de tweets par compte (équité).")
    parser.add_argument("--max-tweets", type=int, default=1500, help="Garde-fou global strict (budget).")
    parser.add_argument("--batch-size", type=int, default=40, help="Tweets par appel Claude.")
    parser.add_argument("--write", action="store_true", help="Écrit feed.json/seen.json (sinon dry-run).")
    parser.add_argument("--feed", default="feed.json")
    parser.add_argument("--seen", default="seen.json")
    args = parser.parse_args()

    _setup_logging()
    try:
        return run_backfill(
            args.config,
            since=_parse_day(args.since),
            until=_parse_day(args.until),
            max_per_account=args.max_per_account,
            max_tweets=args.max_tweets,
            batch_size=args.batch_size,
            write=args.write,
            feed_path=args.feed,
            seen_path=args.seen,
        )
    except Exception as exc:  # noqa: BLE001
        logging.error("Échec du backfill : %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
