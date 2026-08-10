"""Publication du digest sur Telegram via l'API Bot.

On découpe les messages trop longs (limite Telegram : 4096 caractères) en
plusieurs envois, en coupant de préférence entre les blocs (paragraphes).

Subtilité : le digest « détaillé » contient des blocs repliables
`<blockquote expandable>…</blockquote>`. Il ne faut JAMAIS couper un message au
milieu d'un tel bloc, sinon le HTML devient invalide (balise non fermée) et
Telegram rejette l'envoi. Le découpage ci-dessous respecte ces blocs.
"""

from __future__ import annotations

import logging
import re
import time

import requests

log = logging.getLogger(__name__)

TELEGRAM_MAX_LEN = 4096
# On garde une marge sous la limite stricte (4096) pour rester tranquille, même
# après ajout du petit repère « (i/n) » sur les messages découpés.
CHUNK_LIMIT = 4000


def _top_level_blocks(text: str) -> list[str]:
    """Découpe le texte en blocs séparés par une ligne vide, MAIS garde entier
    tout `<blockquote>…</blockquote>` (même s'il contient des lignes vides)."""
    parts = text.split("\n\n")
    blocks: list[str] = []
    buf = ""
    for part in parts:
        buf = part if not buf else buf + "\n\n" + part
        # Tant qu'un <blockquote> est ouvert sans être refermé, on accumule.
        if buf.count("<blockquote") <= buf.count("</blockquote>"):
            blocks.append(buf)
            buf = ""
    if buf:
        blocks.append(buf)
    return blocks


def _hard_line_split(text: str, budget: int) -> list[str]:
    """Coupe `text` en morceaux <= budget, de préférence sur les retours à la
    ligne, sinon en coupant net une ligne trop longue."""
    pieces: list[str] = []
    cur = ""
    for line in text.split("\n"):
        cand = line if not cur else cur + "\n" + line
        if len(cand) <= budget:
            cur = cand
            continue
        if cur:
            pieces.append(cur)
        cur = line
        while len(cur) > budget:  # ligne unique trop longue : coupe nette
            pieces.append(cur[:budget])
            cur = cur[budget:]
    if cur:
        pieces.append(cur)
    return pieces


def _split_oversized_block(block: str, limit: int) -> list[str]:
    """Cas rare : un seul bloc (un sujet) dépasse la limite. On garde un HTML
    valide. S'il contient un `<blockquote>`, on isole l'accroche, puis on refend
    le contenu du bloc repliable en refermant/rouvrant la balise à chaque morceau
    (l'attribut « expandable » est donc préservé sur chaque part)."""
    m = re.search(r"<blockquote[^>]*>", block)
    if not m or "</blockquote>" not in block:
        return _hard_line_split(block, limit)  # pas de blockquote : coupe à plat

    open_tag = m.group(0)
    close_start = block.rfind("</blockquote>")
    before = block[: m.start()].rstrip("\n")
    inner = block[m.end() : close_start]
    after = block[close_start + len("</blockquote>") :].lstrip("\n")

    pieces: list[str] = []
    if before.strip():
        pieces.extend(_hard_line_split(before, limit))
    budget = max(1, limit - len(open_tag) - len("</blockquote>"))
    pieces.extend(open_tag + p + "</blockquote>" for p in _hard_line_split(inner, budget))
    if after.strip():
        pieces.extend(_hard_line_split(after, limit))
    return pieces


def _split_message(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    """Découpe un long message en morceaux <= limit, en cassant entre les blocs
    (jamais au milieu d'un `<blockquote>`)."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    cur = ""
    for block in _top_level_blocks(text):
        if len(block) > limit:
            # Bloc à lui seul trop grand : on vide l'accumulateur puis on le
            # découpe proprement (en préservant le blockquote).
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.extend(_split_oversized_block(block, limit))
            continue
        candidate = block if not cur else cur + "\n\n" + block
        if len(candidate) <= limit:
            cur = candidate
        else:
            chunks.append(cur)
            cur = block
    if cur:
        chunks.append(cur)
    return [c.strip() for c in chunks if c.strip()]


def send_message(
    text: str,
    *,
    bot_token: str,
    chat_id: str,
    timeout: int = 30,
) -> None:
    """Envoie `text` sur le chat/canal Telegram, en plusieurs messages si besoin.
    Quand le texte dépasse la limite Telegram (4096 car.) et se découpe, on ajoute
    un repère « (i/n) » en tête de chaque message pour montrer que c'est une suite."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chunks = _split_message(text)
    total = len(chunks)

    for i, chunk in enumerate(chunks, 1):
        # Repère de pagination seulement s'il y a plusieurs messages.
        body = f"<i>({i}/{total})</i>\n{chunk}" if total > 1 else chunk
        _send_chunk(url, chat_id, body, index=i, total=total, timeout=timeout)
        log.info("Message Telegram envoyé (%d/%d).", i, total)
        if i < total:
            time.sleep(1)  # petite pause pour rester sous les limites de débit


def _send_chunk(
    url: str,
    chat_id: str,
    chunk: str,
    *,
    index: int,
    total: int,
    timeout: int,
    max_retries: int = 3,
) -> None:
    """Envoie un morceau, avec quelques tentatives sur les erreurs transitoires
    (réseau, rate-limit 429, 5xx). Les erreurs « métier » (400 HTML invalide,
    403 bot non-admin…) échouent tout de suite : réessayer n'y changerait rien."""
    payload = {
        "chat_id": chat_id,
        "text": chunk,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise RuntimeError(
                    f"Erreur réseau Telegram sur le morceau {index}/{total} : {exc}"
                ) from exc
            wait = _retry_delay(attempt)
            log.warning("Réseau Telegram KO (%s), nouvelle tentative dans %ds…", exc, wait)
            time.sleep(wait)
            continue

        if resp.ok:
            return

        # 429 (trop de requêtes) et 5xx sont transitoires → on retente.
        transient = resp.status_code == 429 or 500 <= resp.status_code < 600
        if transient and attempt < max_retries:
            # Telegram indique parfois combien de secondes patienter (retry_after).
            wait = _retry_delay(attempt)
            try:
                wait = max(wait, int(resp.json()["parameters"]["retry_after"]))
            except (ValueError, KeyError, TypeError):
                pass
            log.warning(
                "Telegram HTTP %s sur le morceau %d/%d, nouvelle tentative dans %ds…",
                resp.status_code, index, total, wait,
            )
            time.sleep(wait)
            continue

        # L'API Telegram renvoie un JSON explicite en cas d'erreur.
        raise RuntimeError(
            f"Erreur Telegram (HTTP {resp.status_code}) sur le morceau "
            f"{index}/{total} : {resp.text}"
        )


def _retry_delay(attempt: int) -> int:
    """Backoff simple : 2s, 4s, 8s…"""
    return 2 ** attempt
