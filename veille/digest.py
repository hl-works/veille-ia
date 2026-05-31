"""Rédaction du digest par Claude.

On donne à Claude la liste des tweets récents et on lui demande un digest
court, regroupé par thème, prêt à publier sur Telegram (HTML compatible).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import anthropic

from .twitter import Tweet

log = logging.getLogger(__name__)

# Système figé → mis en cache (prompt caching). On y met les consignes stables ;
# les tweets du jour (volatils) vont dans le message utilisateur.
SYSTEM_PROMPT = """\
Tu es le rédacteur d'une veille quotidienne sur l'intelligence artificielle, \
publiée sur un canal Telegram destiné à un public curieux mais non technique \
(commerçants, dirigeants de PME, indépendants).

À partir d'une liste de tweets récents de comptes de référence sur l'IA, \
rédige un digest clair et synthétique.

RÈGLES DE FOND :
- Regroupe l'info par thème (ex. nouveaux modèles, outils, annonces produit, \
débats, ressources), pas compte par compte.
- Garde uniquement ce qui a une vraie valeur d'actualité. Ignore le bavardage, \
l'autopromotion creuse, les tweets sans intérêt informatif.
- Sois factuel et neutre. Ne invente RIEN : si une info n'est pas dans les \
tweets, ne l'ajoute pas. Pas de chiffres ni de dates inventés.
- Explique simplement, sans jargon inutile. Si un terme technique est \
indispensable, glisse une courte explication.
- Vise la concision : 3 à 6 thèmes maximum, quelques lignes chacun.

FORMAT DE SORTIE (HTML compatible Telegram, UNIQUEMENT ces balises) :
- <b>gras</b> pour les titres de section, <i>italique</i> pour les nuances.
- <a href="URL">texte</a> pour les liens. Mets le lien du tweet source sur \
chaque info importante, en utilisant l'URL fournie.
- Pas de <ul>/<li>/<h1> (non supportés). Utilise des puces « • » en début de ligne.
- Pas de bloc de code, pas de Markdown.

Réponds UNIQUEMENT avec le digest. Aucun préambule, aucune phrase du type \
« Voici le digest ». Commence directement par le contenu.\
"""


def _tweets_to_text(tweets: list[Tweet]) -> str:
    """Met les tweets en forme texte pour les passer à Claude."""
    lines: list[str] = []
    for i, tw in enumerate(tweets, 1):
        date = tw.created_at.strftime("%Y-%m-%d %H:%M") if tw.created_at else "date inconnue"
        lines.append(
            f"[{i}] @{tw.author} ({date}) — {tw.like_count} likes, "
            f"{tw.retweet_count} RT\n"
            f"{tw.text}\n"
            f"URL : {tw.url}"
        )
    return "\n\n".join(lines)


def build_digest(tweets: list[Tweet], settings) -> str:
    """Appelle Claude et renvoie le texte HTML du digest."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    user_content = (
        f"Voici les tweets récents (langue du digest : {settings.language}). "
        f"Rédige le digest du {today}.\n\n"
        f"{_tweets_to_text(tweets)}"
    )

    log.info("Rédaction du digest avec %s (%d tweets en entrée)…", settings.model, len(tweets))

    response = client.messages.create(
        model=settings.model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
    )

    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        raise RuntimeError(f"Claude a refusé de répondre : {details}")

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise RuntimeError("Claude n'a renvoyé aucun texte pour le digest.")

    log.info(
        "Digest rédigé (%d caractères ; tokens in=%s out=%s, cache_read=%s).",
        len(text),
        response.usage.input_tokens,
        response.usage.output_tokens,
        getattr(response.usage, "cache_read_input_tokens", 0),
    )
    return text
