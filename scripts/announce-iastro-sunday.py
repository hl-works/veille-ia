"""Annonce hebdomadaire d'iAstro Sunday dans Le Radar iA.

Chaque dimanche, annonce le dernier numéro publié sur hl-consulting.tech
(latest.json) s'il n'a pas encore été annoncé. Un reçu par numéro dans
data/comics-publications/<numéro>.json garantit un seul envoi : réservation
durable AVANT le POST Telegram, jamais de nouvel essai automatique après un
résultat ambigu.

Ce script n'écrit ni ne publie la BD : il annonce ce qui est déjà en ligne.
S'il n'y a pas de numéro récent (semaine en cours ou précédente), il ne fait rien.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from html import unescape
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

ORIGIN = "https://hl-consulting.tech"
LATEST = ORIGIN + "/knowledge-hub/comics/latest.json"
HISTORY = "https://t.me/s/VeilleIA_HL"
RECEIPTS = Path("data/comics-publications")
PARIS = ZoneInfo("Europe/Paris")
ISSUE_RE = re.compile(r"^(\d{4})-W(\d{2})(-r\d+)?$")


def caption(page):
    return ("🗞️ iAstro Sunday est dispo !\n\n"
            "Le best of de l’actu IA de la semaine, au format BD avec Hugo et iAstro.\n\n"
            "📱 À lire tranquillement sur ton téléphone :\n" + page + "\n\nBon dimanche !")


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "iAstroSunday/1.1"}), timeout=40) as r:
        if r.status != 200:
            raise RuntimeError("Public resource unavailable")
        return r.read()


def try_fetch(url):
    try:
        return fetch(url)
    except (HTTPError, URLError, TimeoutError, OSError, RuntimeError):
        return None


def tg(method, payload):
    # Never log the request URL (it contains the bot token).
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    req = Request("https://api.telegram.org/bot" + token + "/" + method,
                  data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=60) as r:
            result = json.load(r)
    except HTTPError as exc:
        raise RuntimeError("Telegram HTTP error " + str(exc.code)) from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError("Telegram response uncertain; inspect channel before any manual retry") from None
    if not result.get("ok"):
        raise RuntimeError("Telegram rejected operation")
    return result["result"]


def now_paris():
    return dt.datetime.now(PARIS)


def latest_issue():
    data = json.loads(fetch(LATEST).decode())
    issue, url = data.get("id", ""), data.get("url", "")
    if not ISSUE_RE.match(issue) or not url.startswith("/knowledge-hub/comics/"):
        raise RuntimeError("latest.json is malformed")
    return issue, ORIGIN + url


def is_recent(issue, today):
    """Le numéro couvre la semaine ISO en cours ou la précédente."""
    m = ISSUE_RE.match(issue)
    year, week = int(m.group(1)), int(m.group(2))
    monday = dt.date.fromisocalendar(year, week, 1)
    this_monday = today - dt.timedelta(days=today.weekday())
    return this_monday - dt.timedelta(days=7) <= monday <= this_monday


def history_check():
    html = unescape(fetch(HISTORY).decode())
    ids = re.findall(r'data-post="(VeilleIA_HL/\d+)"', html)
    if not ids or "Le Radar iA" not in html:
        raise RuntimeError("Cannot verify public channel history")
    return html, ids[-5:]


def verify_live(issue, page_url):
    page = fetch(page_url).decode()
    base = issue.split("-r")[0]
    if "iAstro" not in page or base not in page or "noindex,nofollow" in page:
        raise RuntimeError("Published comic not verified")
    if not re.findall(r'class="scene"', page):
        raise RuntimeError("No published panels")
    for image in set(re.findall(r'<img[^>]+src="([^"]+)"', page)):
        if image.startswith("/knowledge-hub/comics/") and len(fetch(ORIGIN + image)) < 100:
            raise RuntimeError("Comic image unavailable")
    # Couverture facultative : sans elle, on poste un message texte avec bouton.
    for folder in (issue, base):
        url = ORIGIN + "/knowledge-hub/comics/art/" + folder + "/cover-v1.png"
        cover = try_fetch(url)
        if cover and cover.startswith(b"\x89PNG\r\n\x1a\n") and len(cover) <= 9_500_000:
            return url, hashlib.sha256(cover).hexdigest()
    return None, None


def persist(record, receipt):
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    subprocess.run(["git", "add", str(receipt)], check=True)
    subprocess.run(["git", "commit", "-m", f"data: iAstro {record['issue']} Telegram {record['status']}"], check=True)
    # Retry git synchronization only, never the Telegram operation.
    for _ in range(3):
        if subprocess.run(["git", "push", "origin", "HEAD:main"]).returncode == 0:
            return
        subprocess.run(["git", "fetch", "origin", "main"], check=True)
        subprocess.run(["git", "rebase", "origin/main"], check=True)
    raise RuntimeError("Receipt not persisted remotely; do not send/retry automatically")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--only-sunday", action="store_true",
                        help="Ne rien faire si on n'est pas dimanche (Europe/Paris)")
    args = parser.parse_args()

    today = now_paris().date()
    if args.only_sunday and today.weekday() != 6:
        print("Pas dimanche à Paris : rien à faire.")
        return

    issue, page = latest_issue()
    receipt = RECEIPTS / (issue + ".json")
    if receipt.exists():
        old = json.loads(receipt.read_text())
        print(json.dumps({"issue": issue, "existing_receipt": old["status"], "message_id": old.get("message_id")}))
        if old["status"] in ("sent", "observed_existing"):
            print("Dernier numéro déjà annoncé : pas de nouveau iAstro Sunday cette semaine.")
            return
        raise RuntimeError("A previous attempt is reserved or uncertain; manual reconciliation required")
    if not is_recent(issue, today):
        print(f"Dernier numéro publié = {issue}, trop ancien : aucun nouveau numéro à annoncer.")
        return

    me = tg("getMe", {})
    chat = tg("getChat", {"chat_id": os.environ["TELEGRAM_CHANNEL_ID"]})
    if chat.get("type") != "channel" or chat.get("username", "").lower() != "veilleia_hl" or "radar" not in chat.get("title", "").lower():
        raise RuntimeError("Configured Telegram destination does not match Le Radar iA")
    if not tg("getChatMember", {"chat_id": chat["id"], "user_id": me["id"]}).get("can_post_messages"):
        raise RuntimeError("Existing bot cannot publish to the channel")
    html, recent = history_check()
    if page in html:
        print("Announcement already visible in public channel; no send.")
        return
    cover, cover_sha = verify_live(issue, page)
    text = caption(page)
    record = {"issue": issue, "page": page, "cover": cover, "cover_sha256": cover_sha,
              "channel_username": chat["username"], "channel_title": chat["title"],
              "recent_public_messages": recent, "caption": text, "disable_notification": False,
              "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    print(json.dumps({"issue": issue, "channel": chat["title"], "page_verified": True,
                      "cover": bool(cover), "send_requested": args.send}, ensure_ascii=False))
    if not args.send:
        return

    record["status"] = "reserved"
    record["run_id"] = os.environ.get("GITHUB_RUN_ID")
    persist(record, receipt)
    try:
        button = {"inline_keyboard": [[{"text": "📱 Lire la BD", "url": page}]]}
        if cover:
            result = tg("sendPhoto", {"chat_id": chat["id"], "photo": cover, "caption": text,
                                      "disable_notification": False, "reply_markup": button})
        else:
            result = tg("sendMessage", {"chat_id": chat["id"], "text": text,
                                        "disable_notification": False, "reply_markup": button})
        if result.get("chat", {}).get("id") != chat["id"] or not result.get("message_id"):
            raise RuntimeError("Unexpected Telegram result; inspect channel")
        record.update(status="sent", message_id=result["message_id"],
                      message_url="https://t.me/VeilleIA_HL/" + str(result["message_id"]),
                      sent_at=dt.datetime.now(dt.timezone.utc).isoformat())
        persist(record, receipt)
        print(json.dumps({"status": "sent", "issue": issue, "message_url": record["message_url"]}))
    except Exception:
        record["verification_required"] = record["status"] != "sent"
        receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("STOP:", str(exc), file=sys.stderr)
        sys.exit(1)
