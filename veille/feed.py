"""Génération de `feed.json` : la donnée structurée que le site consomme.

Contrat (cf. handoff) — tableau d'entrées, une par sujet marquant :
    {
      "date": "2026-05-19",
      "titre_fr": "...",
      "resume_fr": "...",          # résumé/traduction FR transformative, JAMAIS de recopie
      "tags": ["anthropic", ...],
      "tweet_url": "https://x.com/.../status/...",
      "media": true,
      "auteur_x": "@..."
    }

Règles :
- Plusieurs entrées par jour possibles ; jour sans matière = aucune entrée.
- `feed.json` est CUMULATIF : on append les nouvelles entrées sans réécrire.
- Dédup via `seen.json` (ids de tweets déjà traités) ET via les tweet_url déjà
  présents dans feed.json.
- Copyright : on ne stocke jamais le texte brut du tweet, seulement notre
  résumé FR + le lien source.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from .twitter import Tweet

log = logging.getLogger(__name__)

# Tags de départ recommandés par le handoff. Claude peut en ajouter au besoin,
# mais on garde un socle resserré utile au filtre du site.
BASE_TAGS = [
    "anthropic", "openai", "google", "mistral", "meta", "xai",
    "modeles", "produit", "agents", "recherche", "open-source",
    "talents", "politique-ia", "hardware",
]

# Schéma de sortie strict imposé à Claude (structured outputs).
FEED_SCHEMA = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tweet_id": {"type": "string"},
                    "titre_fr": {"type": "string"},
                    "resume_fr": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["tweet_id", "titre_fr", "resume_fr", "tags"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["entries"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
Tu es le rédacteur en chef d'une veille IA francophone, neutre et anti-hype.

Tu reçois une liste de tweets récents de comptes de référence sur l'IA. Tu dois
SÉLECTIONNER uniquement les sujets vraiment marquants (lancements de modèles ou
de produits, mises à jour majeures, annonces importantes, mouvements de talents,
décisions de politique IA, hardware notable) et produire, pour CHACUN, une entrée
structurée destinée à un site web.

RÈGLES DE SÉLECTION :
- Garde SEULEMENT ce qui a une vraie valeur d'actualité. Ignore le bavardage,
  l'autopromotion, les opinions mineures, les blagues, les détails anecdotiques.
- Si plusieurs tweets parlent du même événement, fais UNE seule entrée (celle du
  tweet source le plus pertinent).
- S'il n'y a vraiment rien de marquant, renvoie une liste `entries` VIDE. Ne
  force jamais une entrée pour remplir.

RÈGLE DE NEUTRALITÉ :
- Couvre tous les acteurs de la même façon (OpenAI, Google, Mistral, Meta, xAI,
  Anthropic…), y compris quand l'info n'est pas flatteuse pour Anthropic/Claude.
  Pas de favoritisme.

RÈGLE COPYRIGHT (DURE) :
- Ne recopie JAMAIS le tweet mot pour mot. `resume_fr` doit être TON texte :
  un résumé / une traduction française reformulée (transformative). Tu peux
  t'appuyer sur les réponses clés si ça aide à comprendre, mais toujours reformulé.

POUR CHAQUE ENTRÉE :
- `tweet_id` : l'identifiant [n] du tweet source dans la liste fournie (ex. "12").
- `titre_fr` : un titre court et factuel en français (pas de clickbait).
- `resume_fr` : 1 à 3 phrases en français, neutres, qui expliquent l'info
  simplement. Pas de jargon inutile.
- `tags` : 1 à 4 tags en minuscules parmi cette liste de départ quand ils
  s'appliquent : {tags}. Tu peux en ajouter un nouveau si vraiment nécessaire,
  mais reste sobre et utile au filtrage.\
""".replace("{tags}", ", ".join(BASE_TAGS))


def _tweets_block(tweets: list[Tweet]) -> str:
    """Liste numérotée des tweets pour Claude. L'index [n] sert de `tweet_id`."""
    lines = []
    for i, tw in enumerate(tweets):
        date = tw.created_at.strftime("%Y-%m-%d") if tw.created_at else "?"
        lines.append(f"[{i}] @{tw.author} ({date})\n{tw.text}")
    return "\n\n".join(lines)


def select_and_write_entries(
    tweets: list[Tweet],
    settings,
    *,
    label: str = "veille",
) -> list[dict]:
    """Demande à Claude de sélectionner les sujets marquants et renvoie une
    liste d'entrées conformes au contrat feed.json (déjà enrichies depuis les
    Tweet : date, tweet_url, media, auteur_x). Liste vide si rien de marquant."""
    if not tweets:
        return []

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    log.info("[%s] sélection des sujets marquants par Claude (%d tweets)…", label, len(tweets))

    response = client.messages.create(
        model=settings.model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": FEED_SCHEMA},
        },
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": _tweets_block(tweets)}],
    )

    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude a refusé : {getattr(response, 'stop_details', None)}")

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Sortie Claude non-JSON : {exc}\n{text[:500]}") from exc

    raw_entries = data.get("entries", [])
    log.info("[%s] %d entrées sélectionnées par Claude.", label, len(raw_entries))

    # On relie chaque entrée à son tweet source (par l'index [n]) pour récupérer
    # les métadonnées vérifiables (url, date, média, auteur) — pas la confiance
    # à Claude pour ces champs factuels.
    entries: list[dict] = []
    for raw in raw_entries:
        try:
            idx = int(raw.get("tweet_id"))
            src = tweets[idx]
        except (TypeError, ValueError, IndexError):
            log.warning("Entrée ignorée : tweet_id invalide (%r)", raw.get("tweet_id"))
            continue
        entries.append(
            {
                "date": (src.created_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d"),
                "titre_fr": str(raw.get("titre_fr", "")).strip(),
                "resume_fr": str(raw.get("resume_fr", "")).strip(),
                "tags": [str(t).strip().lower() for t in raw.get("tags", []) if str(t).strip()],
                "tweet_url": src.url,
                "media": bool(src.has_media),
                "auteur_x": f"@{src.author}" if not src.author.startswith("@") else src.author,
                # champ interne pour la dédup, retiré avant écriture finale
                "_tweet_id": src.id,
            }
        )
    return entries


# ── Persistance : feed.json (cumulatif) + seen.json (mémoire dédup) ──────────

def load_seen(path: str | Path) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        log.warning("seen.json illisible, on repart d'un set vide.")
        return set()


def save_seen(path: str | Path, seen: set[str]) -> None:
    Path(path).write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


def load_feed(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, ValueError):
        log.warning("feed.json illisible, on repart d'une liste vide.")
        return []


def append_entries(
    new_entries: list[dict],
    *,
    feed_path: str | Path,
    seen_path: str | Path,
) -> int:
    """Append les nouvelles entrées dans feed.json (cumulatif), en dédupliquant
    contre seen.json ET contre les tweet_url déjà présents. Met à jour seen.json.
    Renvoie le nombre d'entrées réellement ajoutées."""
    feed = load_feed(feed_path)
    seen = load_seen(seen_path)
    existing_urls = {e.get("tweet_url") for e in feed}

    added = 0
    for entry in new_entries:
        tweet_id = entry.pop("_tweet_id", None)  # retire le champ interne
        if tweet_id and tweet_id in seen:
            continue
        if entry.get("tweet_url") in existing_urls:
            continue
        if not entry.get("titre_fr") or not entry.get("resume_fr"):
            continue
        feed.append(entry)
        existing_urls.add(entry.get("tweet_url"))
        if tweet_id:
            seen.add(tweet_id)
        added += 1

    # Tri chronologique pour un feed propre.
    feed.sort(key=lambda e: e.get("date", ""))
    Path(feed_path).write_text(
        json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    save_seen(seen_path, seen)
    log.info("feed.json : +%d entrées (total %d). seen.json : %d ids.", added, len(feed), len(seen))
    return added
