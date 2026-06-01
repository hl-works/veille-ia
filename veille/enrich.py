"""Enrichissement rétroactif de feed.json : ajoute `score` (0-100) et les tags
marchands aux entrées existantes, SANS re-collecter de tweets.

On repart de notre propre `titre_fr` / `resume_fr` (texte déjà transformatif) :
- aucun appel twitterapi.io (≈ gratuit, juste des appels Claude),
- aucun souci copyright (on ne retouche pas aux sources).

Idempotent : relançable sans risque. Par défaut on (re)score tout le monde et
on complète les tags marchands ; les autres champs sont laissés intacts.

Usage :
    python -m veille.enrich                 # dry-run (n'écrit rien)
    python -m veille.enrich --write         # met à jour feed.json en place
    python -m veille.enrich --batch-size 25 --write
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

import anthropic

from .config import load_settings
from .feed import BASE_TAGS, MERCHANT_TAGS, _clamp_score, load_feed
from pathlib import Path

log = logging.getLogger(__name__)

# Schéma strict : pour chaque entrée, on ne (re)demande QUE score + tags.
ENRICH_SCHEMA = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "idx": {"type": "integer"},
                    "score": {"type": "integer"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["idx", "score", "tags"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["entries"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
Tu es le rédacteur en chef d'une veille IA francophone, neutre et anti-hype.

On te donne des entrées DÉJÀ rédigées (titre + résumé en français). Pour CHACUNE,
tu dois produire deux choses, sans rien réécrire d'autre :

1. `score` : un ENTIER de 0 à 100 = importance ÉDITORIALE pour une audience de
   commerçants, dirigeants de PME et indépendants curieux d'IA. Barème :
     • 80-100 : lancement/MAJ majeur ET directement actionnable pour leur business.
     • 60-79  : annonce importante du secteur, impact indirect mais réel.
     • 40-59  : intéressant à suivre, portée moyenne.
     • 0-39   : niche, très technique ou faible utilité pour cette audience.
   Note de façon discriminante (évite que tout se ressemble).

2. `tags` : la liste COMPLÈTE des tags de l'entrée (thématiques + marchands).
   - Tags thématiques parmi : {tags}.
   - Tags MARCHANDS, à ajouter UNIQUEMENT si le contenu s'y prête vraiment
     (utilité concrète pour un commerçant / une PME), jamais par réflexe : {merchant_tags}.
   Tu peux conserver les tags déjà présents s'ils sont pertinents.

Réponds avec `idx` (l'index fourni) pour chaque entrée. Ne change ni le titre,
ni le résumé, ni aucune autre donnée.\
""".replace("{tags}", ", ".join(BASE_TAGS)).replace("{merchant_tags}", ", ".join(MERCHANT_TAGS))


def _entries_block(entries: list[dict], offset: int) -> str:
    lines = []
    for i, e in enumerate(entries):
        idx = offset + i
        tags = ", ".join(e.get("tags", [])) or "(aucun)"
        lines.append(
            f"[{idx}] {e.get('titre_fr','')}\n{e.get('resume_fr','')}\n"
            f"tags actuels : {tags}"
        )
    return "\n\n".join(lines)


def enrich_feed(config_path: str, *, batch_size: int, write: bool, feed_path: str) -> int:
    settings = load_settings(config_path)
    settings.require_secrets()  # Anthropic + twitterapi (collecte non utilisée ici)

    feed = load_feed(feed_path)
    if not feed:
        log.warning("feed.json vide ou introuvable (%s). Rien à enrichir.", feed_path)
        return 0

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    log.info("Enrichissement de %d entrées (score + tags marchands)…", len(feed))

    updates: dict[int, dict] = {}
    for start in range(0, len(feed), batch_size):
        batch = feed[start : start + batch_size]
        log.info("Lot %d : %d entrées…", start // batch_size + 1, len(batch))
        response = client.messages.create(
            model=settings.model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": ENRICH_SCHEMA},
            },
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": _entries_block(batch, start)}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError(f"Claude a refusé : {getattr(response, 'stop_details', None)}")
        text = next((b.text for b in response.content if b.type == "text"), "")
        data = json.loads(text)
        for raw in data.get("entries", []):
            try:
                idx = int(raw.get("idx"))
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(feed):
                updates[idx] = raw

    # Application des mises à jour (score + tags seulement).
    enriched, with_merchant = 0, 0
    for idx, raw in updates.items():
        feed[idx]["score"] = _clamp_score(raw.get("score"))
        tags = [str(t).strip().lower() for t in raw.get("tags", []) if str(t).strip()]
        # dédup en gardant l'ordre
        feed[idx]["tags"] = list(dict.fromkeys(tags))
        enriched += 1
        if any(t in MERCHANT_TAGS for t in feed[idx]["tags"]):
            with_merchant += 1

    log.info("%d entrées enrichies, dont %d avec au moins un tag marchand.", enriched, with_merchant)

    if not write:
        # Aperçu : top 5 par score + comptage marchands.
        preview = sorted(
            ({"score": feed[i].get("score"), "titre_fr": feed[i].get("titre_fr"),
              "tags": feed[i].get("tags")} for i in updates),
            key=lambda e: e["score"], reverse=True,
        )[:5]
        print("\n" + "=" * 70)
        print("DRY-RUN enrichissement — top 5 par score (rien écrit) :\n")
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        print("=" * 70 + "\n")
        print("Relance avec --write pour mettre à jour feed.json.")
        return 0

    feed.sort(key=lambda e: e.get("date", ""))
    Path(feed_path).write_text(
        json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    log.info("feed.json mis à jour (%d entrées).", len(feed))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrichit feed.json (score + tags marchands).")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--feed", default="feed.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    try:
        return enrich_feed(args.config, batch_size=args.batch_size, write=args.write, feed_path=args.feed)
    except Exception as exc:  # noqa: BLE001
        logging.error("Échec de l'enrichissement : %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
