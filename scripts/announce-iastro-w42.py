"""One explicitly authorized comic announcement; no scheduler and no POST retry."""
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

ISSUE = "2026-W42"
ORIGIN = "https://hl-consulting.tech"
PAGE = ORIGIN + "/knowledge-hub/comics/" + ISSUE + "/"
COVER = ORIGIN + "/knowledge-hub/comics/art/" + ISSUE + "/cover-v1.png"
HISTORY = "https://t.me/s/VeilleIA_HL"
CAPTION = ("🗞️ iAstro Sunday est dispo !\n\n"
           "Le best of de l’actu IA de la semaine, au format BD avec Hugo et iAstro.\n\n"
           "📱 À lire tranquillement sur ton téléphone :\n" + PAGE + "\n\nBon dimanche !")
RECEIPT = Path("data/comics-publications") / (ISSUE + ".json")

def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "iAstroSunday/1.0"}), timeout=40) as r:
        if r.status != 200:
            raise RuntimeError("Public resource unavailable")
        return r.read()

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

def history_check():
    html = unescape(fetch(HISTORY).decode())
    ids = re.findall(r'data-post="(VeilleIA_HL/\d+)"', html)
    if not ids or "Le Radar iA" not in html:
        raise RuntimeError("Cannot verify public channel history")
    return html, ids[-5:]

def verify_live():
    page = fetch(PAGE).decode()
    if 'iAstro' not in page or '2026-W42' not in page or 'noindex,nofollow' in page:
        raise RuntimeError("Published comic not verified")
    if len(re.findall(r'class="scene"', page)) != 24:
        raise RuntimeError("Expected 24 published panels")
    images = set(re.findall(r'<img[^>]+src="([^"]+)"', page))
    for image in images:
        if image.startswith("/knowledge-hub/comics/"):
            if len(fetch(ORIGIN + image)) < 100:
                raise RuntimeError("Comic image unavailable")
    cover = fetch(COVER)
    if not cover.startswith(b"\x89PNG\r\n\x1a\n") or len(cover) > 9_500_000:
        raise RuntimeError("Cover is not a supported Telegram photo")
    return hashlib.sha256(cover).hexdigest()

def persist(record):
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    subprocess.run(["git","add",str(RECEIPT)],check=True)
    subprocess.run(["git","commit","-m",f"data: iAstro {ISSUE} Telegram {record['status']}"],check=True)
    # Retry git synchronization only, never the sendPhoto operation.
    for _ in range(3):
        if subprocess.run(["git","push","origin","HEAD:main"]).returncode == 0:
            return
        subprocess.run(["git","fetch","origin","main"],check=True)
        subprocess.run(["git","rebase","origin/main"],check=True)
    raise RuntimeError("Receipt not persisted remotely; do not send/retry automatically")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--send",action="store_true")
    args=parser.parse_args()
    if RECEIPT.exists():
        old=json.loads(RECEIPT.read_text())
        print(json.dumps({"existing_receipt":old["status"],"message_id":old.get("message_id")}))
        if old["status"] in ("sent","observed_existing"):
            return
        raise RuntimeError("A previous attempt is reserved or uncertain; manual reconciliation required")
    me=tg("getMe",{})
    chat=tg("getChat",{"chat_id":os.environ["TELEGRAM_CHANNEL_ID"]})
    if chat.get("type") != "channel" or chat.get("username","").lower() != "veilleia_hl" or "radar" not in chat.get("title","").lower():
        raise RuntimeError("Configured Telegram destination does not match Le Radar iA")
    membership=tg("getChatMember",{"chat_id":chat["id"],"user_id":me["id"]})
    if not membership.get("can_post_messages"):
        raise RuntimeError("Existing bot cannot publish to the channel")
    html, recent=history_check()
    if PAGE in html:
        print("Announcement already visible in public channel; no send.")
        return
    cover_sha=verify_live()
    record={"issue":ISSUE,"page":PAGE,"cover":COVER,"cover_sha256":cover_sha,
            "channel_username":chat["username"],"channel_title":chat["title"],
            "recent_public_messages":recent,"caption":CAPTION,"disable_notification":False,
            "checked_at":dt.datetime.now(dt.timezone.utc).isoformat()}
    print(json.dumps({"channel":chat["title"],"username":chat["username"],
                      "recent_messages":recent,"page_verified":True,"cover_verified":True,
                      "send_requested":args.send},ensure_ascii=False))
    if not args.send:
        return
    # Reserve before the POST. Any ambiguous result is blocked on the next run.
    record["status"]="reserved"
    record["run_id"]=os.environ.get("GITHUB_RUN_ID")
    persist(record)
    try:
        result=tg("sendPhoto",{"chat_id":chat["id"],"photo":COVER,"caption":CAPTION,
                              "disable_notification":False,
                              "reply_markup":{"inline_keyboard":[[{"text":"📱 Lire la BD","url":PAGE}]]}})
        if result.get("chat",{}).get("id") != chat["id"] or not result.get("message_id"):
            raise RuntimeError("Unexpected Telegram result; inspect channel")
        record.update(status="sent",message_id=result["message_id"],
                      message_url="https://t.me/VeilleIA_HL/"+str(result["message_id"]),
                      sent_at=dt.datetime.now(dt.timezone.utc).isoformat())
        persist(record)
        print(json.dumps({"status":"sent","message_id":result["message_id"],
                          "message_url":record["message_url"],"comic_url":PAGE}))
    except Exception:
        # Keep local evidence as an Actions artifact even if a later git push fails.
        record["verification_required"]=record["status"]!="sent"
        RECEIPT.write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n")
        raise

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print("STOP:",str(exc),file=sys.stderr)
        sys.exit(1)

