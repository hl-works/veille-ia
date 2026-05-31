"""Récupération des tweets via l'API tierce twitterapi.io.

Twitter/X ayant fermé ses accès gratuits, on passe par twitterapi.io : un
service qui renvoie les tweets récents d'un compte contre une clé API
(facturée à l'usage). Auth via l'en-tête `X-API-Key`.

Le parsing est volontairement défensif : si twitterapi.io fait évoluer la
forme exacte de sa réponse, on essaie plusieurs emplacements plausibles
plutôt que de planter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.twitterapi.io"
# Endpoint des derniers tweets d'un utilisateur.
LAST_TWEETS_PATH = "/twitter/user/last_tweets"


@dataclass
class Tweet:
    """Un tweet normalisé, indépendant de la forme brute de l'API."""

    id: str
    author: str
    text: str
    url: str
    created_at: datetime | None
    like_count: int = 0
    retweet_count: int = 0
    is_retweet: bool = False
    is_reply: bool = False


def _parse_date(value) -> datetime | None:
    """Parse une date de tweet. Twitter utilise typiquement le format
    « Tue Dec 10 07:00:00 +0000 2024 ». On gère aussi l'ISO en repli."""
    if not value:
        return None
    if isinstance(value, (int, float)):
        # Timestamp epoch (secondes ou millisecondes)
        ts = value / 1000 if value > 1e12 else value
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    text = str(value).strip()
    # Format Twitter classique
    try:
        return datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        pass
    # Format RFC 2822 / en-têtes HTTP
    try:
        dt = parsedate_to_datetime(text)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        pass
    # Format ISO 8601
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        log.warning("Date de tweet non reconnue : %r", value)
        return None


def _extract_tweet_list(payload: dict) -> list[dict]:
    """Trouve la liste de tweets dans la réponse, quel que soit son emballage."""
    if not isinstance(payload, dict):
        return []
    # Emplacements possibles, du plus probable au moins probable.
    candidates = [
        payload.get("tweets"),
        (payload.get("data") or {}).get("tweets")
        if isinstance(payload.get("data"), dict)
        else None,
        payload.get("data") if isinstance(payload.get("data"), list) else None,
        payload.get("results"),
    ]
    for c in candidates:
        if isinstance(c, list):
            return c
    return []


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize(raw: dict, fallback_author: str) -> Tweet | None:
    """Transforme un tweet brut de l'API en `Tweet`."""
    if not isinstance(raw, dict):
        return None

    tweet_id = str(raw.get("id") or raw.get("id_str") or raw.get("tweet_id") or "")
    text = raw.get("text") or raw.get("full_text") or raw.get("content") or ""

    # Auteur : peut être un sous-objet `author`/`user`, sinon on retombe sur
    # le compte interrogé.
    author = fallback_author
    author_obj = raw.get("author") or raw.get("user")
    if isinstance(author_obj, dict):
        author = (
            author_obj.get("userName")
            or author_obj.get("screen_name")
            or author_obj.get("username")
            or fallback_author
        )

    url = raw.get("url") or raw.get("twitterUrl") or ""
    if not url and tweet_id:
        url = f"https://x.com/{author}/status/{tweet_id}"

    created_at = _parse_date(
        raw.get("createdAt") or raw.get("created_at") or raw.get("timestamp")
    )

    # Détection retweet / réponse (selon les champs disponibles).
    is_retweet = bool(
        raw.get("retweeted_tweet")
        or raw.get("retweetedTweet")
        or raw.get("isRetweet")
        or str(text).startswith("RT @")
    )
    is_reply = bool(
        raw.get("isReply")
        or raw.get("in_reply_to_status_id")
        or raw.get("inReplyToId")
        or raw.get("replyTo")
    )

    return Tweet(
        id=tweet_id,
        author=author,
        text=str(text).strip(),
        url=url,
        created_at=created_at,
        like_count=_as_int(raw.get("likeCount") or raw.get("favorite_count")),
        retweet_count=_as_int(raw.get("retweetCount") or raw.get("retweet_count")),
        is_retweet=is_retweet,
        is_reply=is_reply,
    )


def fetch_user_tweets(username: str, api_key: str, *, timeout: int = 30) -> list[Tweet]:
    """Récupère les derniers tweets d'un compte. Renvoie une liste (vide en
    cas d'erreur réseau/API pour ce compte — on n'interrompt pas toute la
    veille à cause d'un seul compte)."""
    try:
        resp = requests.get(
            BASE_URL + LAST_TWEETS_PATH,
            params={"userName": username},
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.error("Échec de la récupération pour @%s : %s", username, exc)
        return []

    try:
        payload = resp.json()
    except ValueError:
        log.error("Réponse non-JSON pour @%s", username)
        return []

    raw_tweets = _extract_tweet_list(payload)
    tweets = [t for t in (_normalize(r, username) for r in raw_tweets) if t and t.text]
    log.info("@%s : %d tweets récupérés", username, len(tweets))
    return tweets


def collect_recent_tweets(
    accounts: list[str],
    api_key: str,
    *,
    lookback_hours: int,
    max_per_account: int,
    include_retweets: bool,
    include_replies: bool,
) -> list[Tweet]:
    """Récupère, filtre (fenêtre temporelle, retweets/réponses) et dédoublonne
    les tweets de tous les comptes suivis. Triés du plus récent au plus ancien."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    seen_ids: set[str] = set()
    collected: list[Tweet] = []

    for account in accounts:
        tweets = fetch_user_tweets(account, api_key)
        kept = 0
        for tw in tweets:
            if kept >= max_per_account:
                break
            if not include_retweets and tw.is_retweet:
                continue
            if not include_replies and tw.is_reply:
                continue
            # Fenêtre temporelle : si la date est inconnue, on garde par prudence.
            if tw.created_at is not None and tw.created_at < cutoff:
                continue
            if tw.id and tw.id in seen_ids:
                continue
            if tw.id:
                seen_ids.add(tw.id)
            collected.append(tw)
            kept += 1

    collected.sort(key=lambda t: t.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    log.info("Total : %d tweets retenus sur la fenêtre de %dh", len(collected), lookback_hours)
    return collected
