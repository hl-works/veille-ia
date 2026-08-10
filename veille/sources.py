"""Sources complémentaires à X/Twitter, pour enrichir le digest Telegram.

Aujourd'hui : Hacker News (API publique, sans clé) et flux RSS de blogs officiels.
Chaque source produit des objets `Tweet` (la forme commune du pipeline), avec le
champ `source` renseigné ("hn" ou "rss") et `author` lisible (« Hacker News »,
« Blog OpenAI »…). Le digest sait alors les présenter et les attribuer.

Principe DÉFENSIF : une source qui échoue (réseau, format inattendu, flux mort)
est simplement ignorée avec un log — jamais de plantage de toute la veille.

⚠️ Ces sources alimentent le DIGEST TELEGRAM uniquement, pas `feed.json`
(contrat du site inchangé).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests

from .twitter import Tweet

log = logging.getLogger(__name__)

# ── Filtre de pertinence IA (Hacker News est généraliste) ────────────────────
#  On matche des MOTS ENTIERS (bornes \b) : sinon « ai » matcherait « Fastmail »,
#  « impairs »… et laisserait passer du bruit.
_AI_KEYWORDS = (
    "ai", "artificial intelligence", "llm", "llms", "gpt", "chatgpt",
    "claude", "anthropic", "openai", "gemini", "deepmind", "mistral", "llama",
    "grok", "agent", "agents", "machine learning", "ml", "neural network",
    "neural networks", "model", "models", "transformer", "transformers",
    "diffusion", "rag", "fine-tune", "fine-tuning", "inference",
    "hugging face", "huggingface", "prompt", "prompts", "copilot", "cursor",
    "perplexity", "midjourney", "embedding", "embeddings", "multimodal",
    "reasoning", "robotics", "agi",
)

_AI_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _AI_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def _looks_ai_related(text: str) -> bool:
    return bool(_AI_PATTERN.search(text or ""))


# ── Hacker News ──────────────────────────────────────────────────────────────
_HN_API = "https://hacker-news.firebaseio.com/v0"


def fetch_hackernews(
    *,
    lookback_hours: int,
    min_score: int = 60,
    max_scan: int = 60,
    max_keep: int = 12,
    timeout: int = 15,
) -> list[Tweet]:
    """Récupère les meilleures actus IA récentes de Hacker News.

    On lit `beststories` (les mieux notées du moment), on ne garde que celles
    liées à l'IA, publiées dans la fenêtre, au-dessus d'un score minimum.
    """
    try:
        resp = requests.get(f"{_HN_API}/beststories.json", timeout=timeout)
        resp.raise_for_status()
        ids = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("Hacker News : liste indisponible (%s) — source ignorée.", exc)
        return []

    if not isinstance(ids, list):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    kept: list[Tweet] = []
    for story_id in ids[:max_scan]:
        if len(kept) >= max_keep:
            break
        try:
            r = requests.get(f"{_HN_API}/item/{story_id}.json", timeout=timeout)
            r.raise_for_status()
            item = r.json()
        except (requests.RequestException, ValueError):
            continue
        if not isinstance(item, dict) or item.get("type") != "story":
            continue

        score = int(item.get("score", 0) or 0)
        if score < min_score:
            continue

        title = str(item.get("title", "")).strip()
        if not title or not _looks_ai_related(title):
            continue

        created = item.get("time")
        created_at = (
            datetime.fromtimestamp(int(created), tz=timezone.utc) if created else None
        )
        if created_at is not None and created_at < cutoff:
            continue

        hn_url = f"https://news.ycombinator.com/item?id={story_id}"
        url = item.get("url") or hn_url  # article externe, sinon le fil HN (Ask/Show HN)
        comments = int(item.get("descendants", 0) or 0)
        # On glisse le lien de discussion HN dans le texte (utile au lecteur).
        text = title
        if item.get("url"):
            text = f"{title}\n(discussion HN : {hn_url})"

        kept.append(
            Tweet(
                id=f"hn:{story_id}",
                author="Hacker News",
                text=text,
                url=url,
                created_at=created_at,
                like_count=score,          # points HN
                retweet_count=comments,    # nb de commentaires
                source="hn",
            )
        )

    log.info("Hacker News : %d actus IA retenues (score ≥ %d).", len(kept), min_score)
    return kept


# ── Flux RSS de blogs officiels ──────────────────────────────────────────────
def _feed_title(parsed, url: str) -> str:
    """Nom lisible du flux (pour l'attribution)."""
    title = ""
    try:
        title = str(parsed.feed.get("title", "")).strip()
    except Exception:  # noqa: BLE001
        title = ""
    if title:
        return title
    # Repli : le domaine (ex. openai.com).
    host = urlparse(url).netloc.replace("www.", "")
    return host or "RSS"


def _entry_datetime(entry) -> datetime | None:
    import time as _time

    for key in ("published_parsed", "updated_parsed"):
        val = getattr(entry, key, None) or (entry.get(key) if hasattr(entry, "get") else None)
        if val:
            try:
                return datetime.fromtimestamp(_time.mktime(val), tz=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                continue
    return None


def fetch_rss(
    feeds: list[str],
    *,
    lookback_hours: int,
    max_per_feed: int = 4,
    timeout: int = 15,
) -> list[Tweet]:
    """Récupère les billets récents d'une liste de flux RSS/Atom. Défensif :
    un flux mort ou mal formé est ignoré (log), les autres continuent."""
    if not feeds:
        return []
    try:
        import feedparser  # dépendance légère, ajoutée à requirements.txt
    except ImportError:
        log.warning("feedparser non installé — sources RSS ignorées.")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    collected: list[Tweet] = []
    for url in feeds:
        try:
            # On télécharge nous-mêmes (timeout maîtrisé), puis on parse le contenu.
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": "veille-ia/1.0"})
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
        except (requests.RequestException, Exception) as exc:  # noqa: BLE001
            log.warning("RSS %s : indisponible (%s) — ignoré.", url, exc)
            continue

        name = _feed_title(parsed, url)
        kept = 0
        for entry in getattr(parsed, "entries", []) or []:
            if kept >= max_per_feed:
                break
            title = str(getattr(entry, "title", "")).strip()
            link = str(getattr(entry, "link", "")).strip()
            if not title or not link:
                continue
            created_at = _entry_datetime(entry)
            if created_at is not None and created_at < cutoff:
                continue
            collected.append(
                Tweet(
                    id=f"rss:{link}",
                    author=name,
                    text=title,
                    url=link,
                    created_at=created_at,
                    source="rss",
                )
            )
            kept += 1
        if kept:
            log.info("RSS %s : %d billet(s) récent(s).", name, kept)

    log.info("RSS : %d billet(s) au total sur %d flux.", len(collected), len(feeds))
    return collected


# ── YouTube (flux RSS par chaîne, sans clé API) ──────────────────────────────
_YT_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"


def _resolve_youtube_channel_id(spec: str, *, timeout: int = 12) -> str | None:
    """Renvoie un ID de chaîne (UC…). Accepte directement un ID, ou une URL/handle
    (`https://youtube.com/@xxx`) qu'on résout en lisant la page. Défensif."""
    spec = spec.strip()
    if spec.startswith("UC") and len(spec) >= 20 and "/" not in spec:
        return spec
    # Sinon : une URL complète, ou un simple handle (@xxx) → page de la chaîne.
    url = spec if spec.startswith("http") else f"https://www.youtube.com/@{spec.lstrip('@')}"
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        m = re.search(r'"channelId":"(UC[\w-]{20,})"', r.text) or re.search(r"channel/(UC[\w-]{20,})", r.text)
        return m.group(1) if m else None
    except requests.RequestException:
        return None


def fetch_youtube(
    channels: list[str],
    *,
    lookback_hours: int,
    max_per_channel: int = 3,
    ai_filter: bool = False,
    timeout: int = 15,
) -> list[Tweet]:
    """Récupère les vidéos récentes d'une liste de chaînes YouTube via leur flux
    RSS public (aucune clé API). `channels` = IDs `UC…` ou URLs/handles. Si
    `ai_filter`, on ne garde que les titres liés à l'IA (utile pour des chaînes
    généralistes). Défensif : une chaîne injoignable est ignorée."""
    if not channels:
        return []
    try:
        import feedparser
    except ImportError:
        log.warning("feedparser non installé — source YouTube ignorée.")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    collected: list[Tweet] = []
    for spec in channels:
        cid = _resolve_youtube_channel_id(spec)
        if not cid:
            log.warning("YouTube : chaîne non résolue (%s) — ignorée.", spec)
            continue
        try:
            resp = requests.get(_YT_FEED.format(cid), timeout=timeout, headers={"User-Agent": "veille-ia/1.0"})
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
        except (requests.RequestException, Exception) as exc:  # noqa: BLE001
            log.warning("YouTube %s : flux indisponible (%s) — ignoré.", spec, exc)
            continue

        channel = str(parsed.feed.get("title", "")).strip() or spec
        kept = 0
        for entry in getattr(parsed, "entries", []) or []:
            if kept >= max_per_channel:
                break
            title = str(getattr(entry, "title", "")).strip()
            link = str(getattr(entry, "link", "")).strip()
            if not title or not link:
                continue
            if ai_filter and not _looks_ai_related(title):
                continue
            created_at = _entry_datetime(entry)
            if created_at is not None and created_at < cutoff:
                continue
            collected.append(
                Tweet(
                    id=f"yt:{link}",
                    author=channel,
                    text=title,
                    url=link,
                    created_at=created_at,
                    source="youtube",
                )
            )
            kept += 1
        if kept:
            log.info("YouTube %s : %d vidéo(s) récente(s).", channel, kept)

    log.info("YouTube : %d vidéo(s) au total sur %d chaîne(s).", len(collected), len(channels))
    return collected


def collect_extra_sources(settings, *, lookback_hours: int) -> list[Tweet]:
    """Agrège les sources complémentaires activées dans la config. Renvoie une
    liste d'items `Tweet` (source ≠ 'x'), à fusionner avec les tweets pour le
    digest Telegram. Ne touche jamais à feed.json."""
    items: list[Tweet] = []
    if getattr(settings, "include_hackernews", False):
        items += fetch_hackernews(
            lookback_hours=lookback_hours,
            min_score=getattr(settings, "hackernews_min_score", 60),
        )
    if getattr(settings, "include_rss", False):
        items += fetch_rss(
            getattr(settings, "rss_feeds", []),
            lookback_hours=lookback_hours,
        )
    if getattr(settings, "include_youtube", False):
        items += fetch_youtube(
            getattr(settings, "youtube_channels", []),
            lookback_hours=lookback_hours,
            ai_filter=getattr(settings, "youtube_ai_filter", False),
        )
    return items
