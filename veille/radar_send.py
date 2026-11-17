"""Envoi différé du Radar iA : après la mise en ligne de la page du jour.

1. attend que la page du jour réponde (≤ 6 min, sans bloquer l'envoi au-delà) ;
2. rend le journal en pages-images 1080 × 1920 et les envoie en UN album,
   légende = titres du jour + lien vers la page ;
3. repli si le rendu ou l'album échoue : message titres + bouton ; en dernier
   recours, le digest complet. Le canal reçoit toujours sa veille.

Un reçu (radar-pending.json → status) empêche tout double envoi dans le même job.
    python -m veille.radar_send
"""
from __future__ import annotations

from datetime import date
from html import escape
import json
import logging
import os
from pathlib import Path
import tempfile
import time

import requests

from . import journal
from .config import load_settings
from .telegram import send_message

log = logging.getLogger(__name__)
PENDING = Path("radar-pending.json")
SITE = "https://hl-consulting.tech"


def wait_live(url: str, limit: int = 360) -> bool:
    end = time.monotonic() + limit
    while time.monotonic() < end:
        try:
            if requests.get(url, timeout=15, params={"t": int(time.time())}).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(20)
    return False


def fetch(url: str, dest: Path) -> Path | None:
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n":
            dest.write_bytes(r.content)
            return dest
    except requests.RequestException:
        pass
    return None


def caption(digest: str, day: date) -> str:
    titles = journal.headlines(digest)[:7]
    lines = "\n".join(f"• {escape(t, quote=False)}" for t in titles)
    text = (f"<b>🗞️ Le Radar iA — {journal.long_date(day)}</b>\n\n{lines}\n\n"
            f"📰 <a href=\"{journal.journal_url(day)}\">Le journal du jour</a> : le détail, les sources et les deux podcasts.")
    return text[:1020]


def send_album(pages: list[Path], text: str, *, bot_token: str, chat_id: str) -> list[dict]:
    from contextlib import ExitStack
    media, files = [], {}
    with ExitStack() as stack:
        for i, path in enumerate(pages):
            files[f"p{i}"] = (path.name, stack.enter_context(path.open("rb")), "image/png")
            item = {"type": "photo", "media": f"attach://p{i}"}
            if i == 0:
                item.update(caption=text, parse_mode="HTML")
            media.append(item)
        try:
            r = requests.post(f"https://api.telegram.org/bot{bot_token}/sendMediaGroup",
                              data={"chat_id": chat_id, "media": json.dumps(media, ensure_ascii=False)},
                              files=files, timeout=(10, 180))
            payload = r.json()
        except (requests.RequestException, ValueError):
            raise RuntimeError("Album non confirmé ; pas de réessai automatique") from None
    if not r.ok or payload.get("ok") is not True:
        raise RuntimeError(f"Album refusé ({payload.get('description', r.status_code)})")
    return [{"message_id": m.get("message_id")} for m in payload["result"]]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if not PENDING.exists():
        log.info("Rien à envoyer (pas de Radar en attente).")
        return 0
    pending = json.loads(PENDING.read_text(encoding="utf-8"))
    if pending.get("status") in ("sent", "uncertain"):
        log.info("Radar déjà traité (%s).", pending["status"])
        return 0
    settings = load_settings("config.yaml")
    day, digest = date.fromisoformat(pending["date"]), pending["digest"]
    token, chat = settings.telegram_bot_token, settings.telegram_chat_id
    url = journal.journal_url(day)

    def mark(status, **extra):
        pending.update(status=status, **extra)
        PENDING.write_text(json.dumps(pending, ensure_ascii=False), encoding="utf-8")

    if journal.is_calm_day(digest):  # journée calme : le petit mot tel quel
        send_message(pending["message"], bot_token=token, chat_id=chat)
        mark("sent", mode="calme")
        return 0
    live = wait_live(url)
    log.info("Page du jour %s.", "en ligne" if live else "pas encore en ligne (envoi quand même)")
    pages = []
    try:
        from .radar_pages import render
        work = Path(tempfile.mkdtemp())
        portrait = fetch(f"{SITE}/assets/podcast/art/iastro-{day.month:02d}-v1.png", work / "portrait.png")
        signature = fetch(f"{SITE}/assets/podcast/art/hugo-signature-v1.png", work / "signature.png")
        pages = render(digest, day, work / "pages", portrait=portrait, signature=signature)
    except Exception as exc:  # noqa: BLE001
        log.warning("Pages-images indisponibles (%s) → message titres + bouton.", exc)
    if pages:
        try:
            receipts = send_album(pages, caption(digest, day), bot_token=token, chat_id=chat)
            mark("sent", mode="album", pages=len(pages), receipts=receipts)
            log.info("Le Radar iA envoyé : %s pages. ✅", len(pages))
            return 0
        except RuntimeError as exc:
            if "non confirmé" in str(exc):  # l'album est peut-être parti : jamais de doublon
                mark("uncertain", error=str(exc))
                raise
            log.warning("%s → message titres + bouton.", exc)
    text, markup = journal.teaser(digest, day)
    try:
        send_message(text, bot_token=token, chat_id=chat, reply_markup=markup or None)
        mark("sent", mode="titres")
    except Exception:  # noqa: BLE001 — dernier recours : le digest complet
        send_message(pending["message"], bot_token=token, chat_id=chat)
        mark("sent", mode="classique")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
