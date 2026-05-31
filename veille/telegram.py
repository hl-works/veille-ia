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
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=timeout,
        )
        if not resp.ok:
            # L'API Telegram renvoie un JSON explicite en cas d'erreur.
            raise RuntimeError(
                f"Erreur Telegram (HTTP {resp.status_code}) sur le morceau "
                f"{i}/{len(chunks)} : {resp.text}"
            )
        log.info("Message Telegram envoyé (%d/%d).", i, len(chunks))
        if i < len(chunks):
            time.sleep(1)  # petite pause pour rester sous les limites de débit
