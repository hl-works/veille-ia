"""Rédaction du digest par Claude.

On donne à Claude la liste des tweets récents et on lui demande un digest
regroupé par thème, prêt à publier sur Telegram (HTML compatible).

Deux profondeurs possibles (réglage `digest_depth` dans config.yaml) :
- « detaille » (défaut) : digest DÉVELOPPÉ, pensé pour une lecture 100 % autonome
  (hors ligne, sans ouvrir aucun lien). Chaque info marquante est expliquée à fond.
- « essentiel » : digest court à l'ancienne (survol rapide).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import anthropic

from .twitter import Tweet

log = logging.getLogger(__name__)

# ── Consignes communes aux deux modes (format + fond + copyright) ────────────
_COMMON_RULES = """\
Tu es le rédacteur d'une veille quotidienne sur l'intelligence artificielle, \
publiée sur un canal Telegram destiné à un public curieux mais non technique \
(commerçants, dirigeants de PME, indépendants).

À partir d'une liste d'éléments récents issus de PLUSIEURS sources — X/Twitter \
(comptes de référence), Hacker News (actus tech les mieux notées) et blogs \
officiels (via RSS) — rédige un digest clair et fiable.

RÈGLES DE FOND :
- Croise les sources : un même événement rapporté par plusieurs sources (ex. un \
tweet + Hacker News + le blog officiel) est plus important et plus sûr — \
regroupe-les en UN sujet et privilégie le lien le plus fiable (souvent le blog \
officiel). Ne compte pas deux fois le même événement.
- Ne retiens QUE les informations vraiment fortes : lancements de modèles ou \
de produits, mises à jour majeures, annonces importantes, débats marquants. \
Ignore sans pitié le bavardage, l'autopromotion, les opinions mineures, les \
détails techniques anecdotiques.
- Regroupe l'info par thème (ex. nouveaux modèles, annonces produit, IA pour \
les entreprises, débats), jamais compte par compte.
- Sois factuel et neutre. N'invente RIEN : si une info (chiffre, date, prix, \
nom) n'est pas dans les tweets, ne l'écris pas. Tu peux rappeler un contexte \
largement connu pour éclairer, mais sans affirmer de fait nouveau absent des tweets.
- Couvre tous les acteurs de la même façon (OpenAI, Google, Mistral, Meta, xAI, \
Anthropic…), y compris quand l'info n'est pas flatteuse pour l'un d'eux.
- Explique simplement. Si un terme technique est indispensable, glisse une \
courte définition entre parenthèses.

CAS « JOURNÉE CALME » :
- Si rien ne mérite vraiment d'être signalé (que du bruit, des broutilles), ne \
force PAS un digest. Réponds plutôt par un message court et chaleureux du type : \
« Bonjour ☀️ Journée plutôt calme côté IA, rien de majeur à signaler ces \
dernières 24 h. Bonne journée ! » (adapte la formulation). Toujours en HTML Telegram.

FORMAT DE SORTIE (HTML compatible Telegram, UNIQUEMENT ces balises) :
- <b>gras</b> pour les titres de section, <i>italique</i> pour les nuances.
- <a href="URL">texte</a> pour les liens. Utilise TOUJOURS l'URL exacte fournie \
avec le tweet (ne fabrique jamais d'URL).
- <blockquote expandable>…</blockquote> pour un bloc « détails » repliable que le \
lecteur touche pour dérouler (voir la structure ci-dessous). Ne JAMAIS imbriquer \
un blockquote dans un autre.
- Pas de <ul>/<li>/<h1>/<h2> (non supportés). Utilise des puces « • » en début de ligne.
- Pas de bloc de code, pas de Markdown (ni #, ni **, ni []()).

RÈGLE COPYRIGHT (DURE) :
- Ne recopie JAMAIS un tweet mot pour mot. Tout ce que tu écris est TA \
reformulation / traduction française. Le lien source sert de référence, pas de \
copier-coller.

Réponds UNIQUEMENT avec le digest. Aucun préambule, aucune phrase du type \
« Voici le digest ». Commence directement par le contenu.\
"""

# ── Corps « détaillé » : deux niveaux (survol visible + détails repliables) ──
_DETAILED_BODY = """\

OBJECTIF CLÉ — LECTURE AUTONOME, HORS LIGNE, 100 % EN FRANÇAIS (TRÈS IMPORTANT) :
Le lecteur consulte souvent ce digest HORS LIGNE et n'ouvrira AUCUN lien externe. \
Tout doit se comprendre rien qu'en te lisant, et TOUT est rédigé en français — y \
compris les blocs « détails ». Les liens X ne servent que de référence, jamais à \
la compréhension.

Le digest a DEUX niveaux :
- « L'ESSENTIEL » : une lecture visible et confortable d'environ 1 à 2 MINUTES \
  (pas un simple TL;DR de 30 secondes). C'est le cœur : le lecteur doit y trouver \
  l'info et le pourquoi, sans avoir à dérouler quoi que ce soit.
- Les « DÉTAILS » : sous chaque sujet, un bloc repliable que le lecteur touche \
  pour aller plus loin — la version longue et exhaustive.

STRUCTURE ATTENDUE (dans cet ordre) :

1. <b>📌 L'essentiel du jour</b>
   Le corps principal, pensé pour 1 à 2 minutes de lecture. Regroupe l'info en \
   3 à 6 thèmes. Pour CHAQUE sujet marquant :
   a) un titre de section en <b>gras</b> précédé d'un emoji pertinent ;
   b) 2 à 4 phrases VISIBLES (pas repliées) qui donnent vraiment l'info : quoi, \
      les éléments clés, et pourquoi ça compte. C'est lisible directement, sans \
      rien ouvrir. Reste clair et sans jargon.
   c) JUSTE en dessous (retour à la ligne simple), un bloc « détails » repliable, \
      ENTIÈREMENT EN FRANÇAIS, qui reprend le sujet EN ENTIER pour qui veut creuser : \
      tout le contenu (surtout si la source est un FIL de plusieurs tweets du même \
      auteur — reprends alors TOUT le propos, pas seulement le début), les chiffres \
      et détails, le contexte, et « ce que ça change pour vous » (commerçant / PME \
      quand c'est pertinent). Termine par la ou les source(s). Format EXACT du bloc :
      <blockquote expandable>🔎 <b>Pour aller plus loin —</b> …6 à 12 phrases…  \
Source : <a href="URL">@compte</a></blockquote>

2. <b>✨ La phrase du jour</b> (optionnel) : une idée forte reformulée, si un \
   tweet s'y prête vraiment.

RÈGLES DE MISE EN FORME :
- Sépare chaque sujet par une LIGNE VIDE. À l'intérieur d'un sujet (essentiel \
  visible + bloc détails), n'utilise que des retours à la ligne SIMPLES.
- Ne mets PAS de blockquote autour du texte visible : le bloc repliable est \
  réservé aux « détails » d'un sujet.
- Le texte VISIBLE (« l'essentiel ») doit se suffire à lui-même. Le bloc \
  « détails » est un bonus de profondeur — jamais indispensable, jamais une \
  simple répétition : il apporte réellement plus (le fil complet, les chiffres, \
  les implications).\
"""

# ── Corps « essentiel » : survol rapide à l'ancienne ─────────────────────────
_CONCISE_BODY = """\

STRUCTURE ATTENDUE :
- Regroupe l'info par thème. 3 à 6 thèmes maximum, quelques lignes chacun.
- Titres de section en <b>gras</b>, puces « • ».
- Mets le lien du tweet source sur chaque info importante.
- Vise la concision : un survol rapide, pas un dossier de fond.\
"""


def _system_prompt(depth: str) -> str:
    """Assemble le prompt système selon la profondeur voulue."""
    body = _CONCISE_BODY if depth == "essentiel" else _DETAILED_BODY
    return _COMMON_RULES + "\n" + body


def _source_header(tw: Tweet, index: int, date: str) -> str:
    """Ligne d'en-tête d'un item, adaptée à sa source (X, Hacker News, RSS)."""
    source = getattr(tw, "source", "x")
    if source == "hn":
        return (
            f"[{index}] Hacker News ({date}) — {tw.like_count} points, "
            f"{tw.retweet_count} commentaires"
        )
    if source == "rss":
        return f"[{index}] {tw.author} — blog officiel ({date})"
    # X / Twitter (défaut)
    media = " [média]" if tw.has_media else ""
    thread = (
        f" [FIL de {tw.thread_parts} tweets du même auteur]"
        if getattr(tw, "is_thread", False) else ""
    )
    return (
        f"[{index}] @{tw.author} ({date}) — {tw.like_count} likes, "
        f"{tw.retweet_count} RT{media}{thread}"
    )


def _tweets_to_text(tweets: list[Tweet]) -> str:
    """Met les items (tweets + Hacker News + RSS) en forme texte pour Claude."""
    lines: list[str] = []
    for i, tw in enumerate(tweets, 1):
        date = tw.created_at.strftime("%Y-%m-%d %H:%M") if tw.created_at else "date inconnue"
        lines.append(f"{_source_header(tw, i, date)}\n{tw.text}\nURL : {tw.url}")
    return "\n\n".join(lines)


def build_digest(tweets: list[Tweet], settings, *, for_date: datetime | None = None) -> str:
    """Appelle Claude et renvoie le texte HTML du digest. `for_date` permet de
    dater le digest d'un jour passé (rejeu multi-jours) ; défaut = aujourd'hui."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    depth = getattr(settings, "digest_depth", "detaille")
    system_prompt = _system_prompt(depth)

    day = (for_date or datetime.now(timezone.utc)).strftime("%d/%m/%Y")
    user_content = (
        f"Voici les tweets (langue du digest : {settings.language}). "
        f"Rédige le digest du {day}.\n\n"
        f"{_tweets_to_text(tweets)}"
    )

    # Le mode détaillé produit un texte plus long → on desserre le plafond de sortie.
    max_tokens = 8000 if depth == "essentiel" else 14000

    log.info(
        "Rédaction du digest (%s, mode « %s ») — %d tweets en entrée…",
        settings.model, depth, len(tweets),
    )

    response = client.messages.create(
        model=settings.model,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        system=[
            {
                "type": "text",
                "text": system_prompt,
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
