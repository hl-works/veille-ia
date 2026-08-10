"""Publication du digest sur Telegram via l'API Bot.

On découpe les messages trop longs (limite Telegram : 4096 caractères) en
plusieurs envois, en coupant de préférence sur des sauts de paragraphe.
"""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

TELEGRAM_MAX_LEN = 4096
# On garde une marge sous la limite stricte pour être tranquille.
CHUNK_LIMIT = 3900


def _split_message(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    """Découpe un long message en morceaux <= limit, en cassant sur les
    sauts de ligne quand c'est possible."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        # Cherche le dernier saut de paragraphe, puis de ligne, dans la fenêtre.
        cut = window.rfind("\n\n")
        if cut == -1:
            cut = window.rfind("\n")
        if cut == -1:
            cut = limit  # aucun saut : on coupe net
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return [c for c in chunks if c]


def send_message(
    text: str,
    *,
    bot_token: str,
    chat_id: str,
    timeout: int = 30,
) -> None:
    """Envoie `text` sur le chat/canal Telegram, en plusieurs messages si besoin."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chunks = _split_message(text)

    for i, chunk in enumerate(chunks, 1):
        _send_chunk(url, chat_id, chunk, index=i, total=len(chunks), timeout=timeout)
        log.info("Message Telegram envoyé (%d/%d).", i, len(chunks))
        if i < len(chunks):
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
