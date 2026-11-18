"""« La Semaine » du Podcast iA : un épisode long qui résume toute la semaine.

Demande de Hugo (17/11/2026) : pour ceux qui n'ont pas le temps, un seul podcast
par semaine, plus long et plus condensé, publié le dimanche pour une écoute le lundi.

Source : les veilles quotidiennes enregistrées dans journal/AAAA-MM-JJ.json.
Même voix, même habillage, même format iAstro/Victoria que le Débrief.

Destination : en privé à Hugo tant que WEEKLY_PUBLIC n'est pas « true » (le podcast
est validé par Hugo avant toute publication) ; sinon canal Telegram + flux RSS.

    python -m veille.semaine [--date AAAA-MM-JJ] [--send] [--site CHECKOUT_DU_SITE]
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from zoneinfo import ZoneInfo

from . import audio
from .config import load_settings
from .journal import MONTHS, _text

log = logging.getLogger(__name__)
MIN_DAYS = 3


def week_bounds(today: date) -> tuple[str, date, date]:
    monday = today - timedelta(days=today.weekday())
    y, w, _ = monday.isocalendar()
    return f"semaine-{y}-W{w:02d}", monday, monday + timedelta(days=6)


def period_label(monday: date, sunday: date) -> str:
    if monday.month == sunday.month:
        return f"du {monday.day} au {sunday.day} {MONTHS[sunday.month - 1]}"
    return f"du {monday.day} {MONTHS[monday.month - 1]} au {sunday.day} {MONTHS[sunday.month - 1]}"


def week_snapshot(journal_dir: Path, monday: date, sunday: date) -> dict:
    days, sources = [], []
    for path in sorted(Path(journal_dir).glob("*.json")):
        day = date.fromisoformat(path.stem)
        if not monday <= day <= sunday:
            continue
        digest = json.loads(path.read_text(encoding="utf-8"))["digest"]
        sources += re.findall(r'href="(https?://[^"]+)"', digest)
        days.append(f"=== Veille du {day.isoformat()} ===\n{_text(digest.replace(chr(10), ' ¶ ')).replace(' ¶ ', chr(10))}")
    if len(days) < MIN_DAYS:
        raise RuntimeError(f"Seulement {len(days)} veille(s) cette semaine : épisode non produit")
    return {"date": sunday.isoformat(), "text": "\n\n".join(days),
            "sources": list(dict.fromkeys(sources)), "days": len(days)}


def run(today: date, out: Path, *, send: bool, site: Path | None) -> dict:
    settings = load_settings("config.yaml")
    cfg = audio.audio_config()
    slot, monday, sunday = week_bounds(today)
    snapshot = week_snapshot(Path("journal"), monday, sunday)
    out.mkdir(parents=True, exist_ok=True)
    lexicon = (audio.load_lexicon(cfg.get("lexique", "lexique.yaml"))
               if str(cfg.get("lexique_actif", "true")).lower() != "false" else {})
    with tempfile.TemporaryDirectory() as music:
        pieces = audio._pieces(cfg, Path(music))
        script = audio.build_script(snapshot, settings, cfg["format"], "semaine")
        (out / "transcript.txt").write_text(audio.clean_script(script), encoding="utf-8")
        spoken = audio.spoken_text(script, lexicon)
        (out / "spoken.txt").write_text(spoken, encoding="utf-8")
        mp3 = out / "semaine.mp3"
        audio.render(spoken, audio.get_provider(cfg), mp3, pieces)
    seconds = audio.duration_seconds(mp3)
    public = os.environ.get("WEEKLY_PUBLIC", "").lower() == "true"
    meta = {"id": slot, "date": sunday.isoformat(), "period": period_label(monday, sunday),
            "days": snapshot["days"], "seconds": seconds, "public": public, "telegram_sent": False}
    season = {12: "hiver", 1: "hiver", 2: "hiver", 3: "printemps", 4: "printemps", 5: "printemps",
              6: "ete", 7: "ete", 8: "ete"}.get(sunday.month, "automne")
    cover = None
    if site:
        cover = site / f"assets/podcast/semaine/cover-{season}.jpg"
        if not cover.is_file():
            cover = site / "assets/podcast/semaine/cover.jpg"
    thumb = None
    if cover and cover.is_file():
        thumb = out / "semaine-thumbnail.jpg"
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(cover), "-vf", "scale=320:320",
                        "-q:v", "3", str(thumb)], check=True, timeout=60)
    (out / "semaine.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if send:
        from .telegram import send_audio
        chat_id = settings.telegram_chat_id if public else os.environ["TELEGRAM_AUTHORIZED_USER_ID"]
        meta["telegram_receipt"] = send_audio(
            mp3, day=sunday.isoformat(), duration=seconds, bot_token=settings.telegram_bot_token,
            chat_id=chat_id, title_prefix="La Semaine · Le Podcast IA", thumbnail=thumb, podcast_links=public,
            caption_suffix=(f"toute la semaine {meta['period']} en un épisode" if public else
                            f"À VALIDER — toute la semaine {meta['period']} (non publié)"))
        meta["telegram_sent"] = True
        (out / "semaine.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if public and site:
        publish_site(site, out, meta, cover)
    return meta


def publish_site(site: Path, out: Path, meta: dict, cover: Path | None) -> None:
    """Archive + platform-episodes.json (flux RSS) ; le build du flux est fait par le workflow."""
    folder = site / "assets/podcast/archive" / meta["id"]
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out / "semaine.mp3", folder / "full.mp3")
    data = (folder / "full.mp3").read_bytes()
    track = {"src": f"/assets/podcast/archive/{meta['id']}/full.mp3", "seconds": meta["seconds"],
             "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if cover and cover.is_file():
        shutil.copyfile(cover, folder / "full-cover-v2.jpg")
        track.update(image=f"/assets/podcast/archive/{meta['id']}/full-cover-v2.jpg",
                     image_sha256=hashlib.sha256((folder / "full-cover-v2.jpg").read_bytes()).hexdigest())
    # 3e émission « La Semaine iA » : flux séparé (assets/podcast/semaine/feed.xml).
    manifest_path = site / "assets/podcast/semaine/episodes.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"episodes": []}
    manifest["episodes"] = [e for e in manifest["episodes"] if e.get("id") != meta["id"]] + [{
        "date": meta["date"], "id": meta["id"], "title": f"La Semaine iA — {meta['period']}",
        "description": (f"Toute l'actualité IA de la semaine {meta['period']}, en un seul épisode : "
                        "les sujets qui ont compté, comment ils ont évolué, ce qu'il faut surveiller. "
                        "Émission de Hugo LaHutte, avec iAstro et des voix de synthèse."),
        "full": track}]
    manifest["episodes"].sort(key=lambda e: e["date"], reverse=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--site", type=Path)
    ap.add_argument("--output", type=Path, default=Path("semaine-output"))
    args = ap.parse_args()
    today = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo("Europe/Paris")).date()
    meta = run(today, args.output, send=args.send, site=args.site)
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
