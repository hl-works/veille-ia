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
    has_media: bool = False
    # Chaînage de fil : à quel tweet (et quel compte) celui-ci répond. Sert à
    # recoller les FILS d'un même auteur (self-thread) sans ramasser la conv.
    reply_to_tweet_id: str | None = None
    reply_to_user: str | None = None
    # Rempli quand plusieurs tweets d'un même auteur ont été recollés en un seul.
    is_thread: bool = False
    thread_parts: int = 1


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

    # À quel tweet celui-ci répond (parent direct) et à quel compte.
    reply_to_tweet_id = raw.get("inReplyToId") or raw.get("in_reply_to_status_id") \
        or raw.get("in_reply_to_status_id_str")
    reply_to_tweet_id = str(reply_to_tweet_id) if reply_to_tweet_id else None
    reply_to_user = (
        raw.get("inReplyToUsername")
        or raw.get("in_reply_to_screen_name")
        or raw.get("inReplyToUserName")
    )
    reply_to_user = str(reply_to_user).lstrip("@") if reply_to_user else None

    is_reply = bool(
        raw.get("isReply")
        or reply_to_tweet_id
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
        has_media=_detect_media(raw),
        reply_to_tweet_id=reply_to_tweet_id,
        reply_to_user=reply_to_user,
    )


def _detect_media(raw: dict) -> bool:
    """Détecte la présence d'une image/vidéo dans le tweet (pour `media` du
    feed). On regarde plusieurs emplacements possibles selon la forme de l'API."""
    # Champs « entities/extended_entities » façon API Twitter classique.
    for key in ("extendedEntities", "extended_entities", "entities"):
        ent = raw.get(key)
        if isinstance(ent, dict) and ent.get("media"):
            return True
    # Champs à plat parfois exposés par twitterapi.io.
    for key in ("media", "mediaUrls", "photos", "videos", "extendedMedia"):
        val = raw.get(key)
        if val:  # liste/objet non vide
            return True
    return False


def _stitch_threads(tweets: list[Tweet]) -> list[Tweet]:
    """Recolle les FILS d'un même auteur : quand un compte poste plusieurs tweets
    qui se répondent à eux-mêmes (self-thread / tweetstorm), on fusionne tout le
    contenu en UNE seule entrée (au tweet racine), pour ne rien perdre du propos.

    On ne touche PAS aux réponses adressées à d'autres comptes (la « conv ») :
    comme la liste passée ici ne contient que les tweets d'UN auteur, un lien de
    réponse dont la cible est dans la liste = forcément une suite du même auteur.
    """
    by_id = {t.id: t for t in tweets if t.id}
    children_of: dict[str, list[Tweet]] = {}
    child_ids: set[str] = set()
    for t in tweets:
        parent = t.reply_to_tweet_id
        if parent and parent in by_id and parent != t.id:
            children_of.setdefault(parent, []).append(t)
            child_ids.add(t.id)

    if not child_ids:  # aucun fil : rien à faire
        return tweets

    def _newest(t: Tweet) -> datetime:
        return t.created_at or datetime.min.replace(tzinfo=timezone.utc)

    result: list[Tweet] = []
    for t in tweets:
        if t.id in child_ids:
            continue  # sera fusionné dans sa racine
        # Rassemble la racine + tous ses descendants (fil linéaire ou ramifié).
        chain: list[Tweet] = []
        stack = [t]
        seen: set[str] = set()
        while stack:
            node = stack.pop()
            if node.id in seen:
                continue
            seen.add(node.id)
            chain.append(node)
            stack.extend(children_of.get(node.id, []))
        if len(chain) == 1:
            result.append(t)
            continue
        chain.sort(key=_newest)  # ordre chronologique de lecture du fil
        result.append(_merge_chain(chain))
    return result


def _merge_chain(chain: list[Tweet]) -> Tweet:
    """Fusionne un fil (déjà trié) en un seul Tweet, ancré sur le tweet racine."""
    root = chain[0]
    combined = "\n\n".join(p.text for p in chain if p.text)
    latest = max(
        (p.created_at for p in chain if p.created_at),
        default=root.created_at,
    )
    return Tweet(
        id=root.id,
        author=root.author,
        text=combined,
        url=root.url,
        created_at=latest,  # activité la plus récente du fil (pour la fenêtre)
        like_count=max((p.like_count for p in chain), default=0),
        retweet_count=max((p.retweet_count for p in chain), default=0),
        is_retweet=False,
        is_reply=False,  # une fois recollé, le fil est un contenu autonome
        has_media=any(p.has_media for p in chain),
        reply_to_tweet_id=root.reply_to_tweet_id,
        reply_to_user=root.reply_to_user,
        is_thread=True,
        thread_parts=len(chain),
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
    tweets = _stitch_threads(tweets)  # recolle les fils du même auteur
    threads = sum(1 for t in tweets if t.is_thread)
    log.info(
        "@%s : %d tweets récupérés%s", username, len(tweets),
        f" (dont {threads} fil(s) recollé(s))" if threads else "",
    )
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


ADVANCED_SEARCH_PATH = "/twitter/tweet/advanced_search"


def advanced_search(
    accounts: list[str],
    api_key: str,
    *,
    since: datetime,
    until: datetime,
    max_per_account: int,
    max_total: int,
    max_pages_per_account: int = 5,
    include_retweets: bool = False,
    include_replies: bool = False,
    timeout: int = 30,
) -> list[Tweet]:
    """Récupère les tweets d'une période donnée (backfill), équitablement
    réparti : chaque compte contribue jusqu'à `max_per_account`, et `max_total`
    sert de garde-fou global ultime (leçon Patel : pas de boucle infinie, cap
    strict). Le quota par compte évite que les premiers comptes de la liste
    raflent tout le budget.

    Utilise l'endpoint `advanced_search` de twitterapi.io avec une requête
    `from:<compte> since:<date> until:<date>` et la pagination par curseur.
    """
    since_str = since.strftime("%Y-%m-%d_%H:%M:%S_UTC")
    until_str = until.strftime("%Y-%m-%d_%H:%M:%S_UTC")
    seen_ids: set[str] = set()
    collected: list[Tweet] = []

    for account in accounts:
        if len(collected) >= max_total:
            log.warning("Plafond global max_total=%d atteint, on arrête.", max_total)
            break

        query = f"from:{account} since:{since_str} until:{until_str}"
        cursor = ""
        # On collecte d'abord TOUT le brut du compte (self-replies compris) pour
        # pouvoir recoller les fils AVANT de filtrer les réponses. Sinon les
        # suites d'un thread (qui sont des self-replies) seraient jetées.
        raw_account: list[Tweet] = []
        for _ in range(max_pages_per_account):
            params = {"query": query, "queryType": "Latest"}
            if cursor:
                params["cursor"] = cursor
            try:
                resp = requests.get(
                    BASE_URL + ADVANCED_SEARCH_PATH,
                    params=params,
                    headers={"X-API-Key": api_key},
                    timeout=timeout,
                )
                resp.raise_for_status()
                payload = resp.json()
            except (requests.RequestException, ValueError) as exc:
                log.error("advanced_search @%s : %s", account, exc)
                break

            for r in _extract_tweet_list(payload):
                tw = _normalize(r, account)
                if tw and tw.text and tw.id:
                    raw_account.append(tw)

            # Pagination : has_next_page / next_cursor
            if not payload.get("has_next_page") or not payload.get("next_cursor"):
                break
            cursor = payload["next_cursor"]

        # Recolle les fils du compte, puis filtre (retweets/réponses/dédup) et
        # applique le quota par compte.
        kept_this_account = 0
        for tw in _stitch_threads(raw_account):
            if kept_this_account >= max_per_account or len(collected) >= max_total:
                break
            if not include_retweets and tw.is_retweet:
                continue
            if not include_replies and tw.is_reply:
                continue
            if tw.id in seen_ids:
                continue
            seen_ids.add(tw.id)
            collected.append(tw)
            kept_this_account += 1

        threads = sum(1 for t in collected[len(collected) - kept_this_account:] if t.is_thread)
        log.info(
            "Backfill @%s : %d tweets%s (total %d)",
            account, kept_this_account,
            f" (dont {threads} fil(s))" if threads else "", len(collected),
        )

    collected.sort(key=lambda t: t.created_at or datetime.min.replace(tzinfo=timezone.utc))
    log.info(
        "Backfill : %d tweets sur %s → %s (%d/compte, plafond global %d)",
        len(collected), since_str, until_str, max_per_account, max_total,
    )
    return collected
