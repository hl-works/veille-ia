"""Écouteur de commandes Telegram — SANS serveur.

Sondé périodiquement par GitHub Actions (getUpdates). Quand l'utilisateur
AUTORISÉ envoie une commande au bot en message privé, on la traite. C'est ce qui
permet un « menu Telegram » pour lancer la mise à jour sans passer par GitHub.

Commandes (en DM au bot) :
    /maj [N]     → republie les N derniers jours (défaut 1) sur le canal
    /aide        → rappelle les commandes disponibles

Sécurité / robustesse :
- On n'agit QUE pour l'ID Telegram autorisé (secret TELEGRAM_AUTHORIZED_USER_ID).
- On IGNORE les commandes trop vieilles (backlog) pour ne pas rejouer par surprise.
- On confirme (flush) les updates AVANT de lancer le rejeu : au pire une commande
  est perdue (à renvoyer), jamais exécutée deux fois.
- Pas de webhook requis, pas de fichier d'état à committer : la confirmation
  getUpdates(offset=...) côté Telegram suffit à ne pas retraiter les mêmes messages.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

import requests

from .config import load_settings
from .replay import (
    DEFAULT_MAX_PAGES,
    DEFAULT_MAX_PER_ACCOUNT,
    DEFAULT_MAX_PER_DAY,
    run_replay,
)

log = logging.getLogger(__name__)

API = "https://api.telegram.org"
STALE_SECONDS = 15 * 60   # on ignore une commande reçue il y a plus de 15 min
MAX_DAYS = 14             # garde-fou : jamais plus de 14 jours d'un coup

BOT_COMMANDS = [
    {"command": "maj", "description": "Republier les N derniers jours (ex. /maj 7)"},
    {"command": "aide", "description": "Afficher l'aide"},
]

HELP_TEXT = (
    "🤖 <b>Commandes de la Veille IA</b>\n\n"
    "• <code>/maj</code> — republie le dernier jour au nouveau format\n"
    "• <code>/maj N</code> — republie les N derniers jours (ex. <code>/maj 7</code>, "
    f"max {MAX_DAYS})\n"
    "• <code>/aide</code> — affiche ce message\n\n"
    "Le digest quotidien de 7h reste automatique, rien à faire pour lui."
)


def _tg(token: str, method: str, **body):
    resp = requests.post(f"{API}/bot{token}/{method}", json=body, timeout=45)
    resp.raise_for_status()
    return resp.json()


def _send(token: str, chat_id, text: str) -> None:
    try:
        _tg(token, "sendMessage", chat_id=chat_id, text=text,
            parse_mode="HTML", disable_web_page_preview=True)
    except requests.RequestException as exc:
        log.warning("Envoi de l'accusé Telegram échoué : %s", exc)


def _publish_menu(token: str) -> None:
    """Fait apparaître les commandes dans le menu « / » du bot (idempotent)."""
    try:
        _tg(token, "setMyCommands", commands=BOT_COMMANDS)
    except requests.RequestException as exc:
        log.warning("setMyCommands échoué : %s", exc)


def _parse_command(text: str) -> tuple[str, int] | None:
    """Renvoie ('maj', jours) / ('aide', 0) / None. Tolère /maj@MonBot 7."""
    text = (text or "").strip()
    if not text.startswith("/"):
        return None
    parts = text.split()
    verb = parts[0][1:].split("@", 1)[0].lower()  # enlève le / et un @mention
    if verb in {"maj", "update", "rejeu"}:
        days = 1
        if len(parts) > 1:
            try:
                days = int(parts[1])
            except ValueError:
                days = 1
        return ("maj", max(1, min(MAX_DAYS, days)))
    if verb in {"aide", "help", "start"}:
        return ("aide", 0)
    return None


def run_listener(config_path: str) -> int:
    settings = load_settings(config_path)
    if not settings.accounts:
        log.error("Aucun compte dans config.yaml. Rien à faire.")
        return 1
    settings.require_secrets()  # Anthropic + twitterapi (nécessaires au rejeu)

    token = settings.telegram_bot_token
    if not token or not settings.telegram_chat_id:
        log.error("Secrets Telegram manquants (bot token / chat id) : écouteur inactif.")
        return 1

    authorized = os.environ.get("TELEGRAM_AUTHORIZED_USER_ID", "").strip()
    if not authorized:
        log.error(
            "TELEGRAM_AUTHORIZED_USER_ID absent → par sécurité on n'exécute aucune "
            "commande. Ajoute ton ID Telegram numérique dans les secrets du dépôt."
        )
        return 1

    _publish_menu(token)

    try:
        updates = _tg(token, "getUpdates", timeout=0, allowed_updates=["message"]).get("result", [])
    except requests.RequestException as exc:
        log.error("getUpdates échoué : %s", exc)
        return 1

    if not updates:
        log.info("Aucune nouvelle commande.")
        return 0

    # Confirme (flush) TOUT de suite pour ne jamais retraiter ces updates.
    max_id = max(u["update_id"] for u in updates)
    try:
        _tg(token, "getUpdates", offset=max_id + 1, timeout=0)
    except requests.RequestException as exc:
        log.warning("Confirmation getUpdates échouée (%s) — on continue prudemment.", exc)

    now = datetime.now(timezone.utc).timestamp()
    # On ne retient que la DERNIÈRE commande valide de l'utilisateur autorisé.
    chosen: tuple[str, int] | None = None
    chosen_chat = None
    ignored_unauth = 0
    for u in updates:
        msg = u.get("message")
        if not msg:
            continue
        frm = msg.get("from") or {}
        if str(frm.get("id")) != authorized:
            ignored_unauth += 1
            continue
        if now - float(msg.get("date", 0)) > STALE_SECONDS:
            log.info("Commande ignorée (trop ancienne) : %r", msg.get("text"))
            continue
        parsed = _parse_command(msg.get("text", ""))
        if parsed:
            chosen = parsed
            chosen_chat = msg["chat"]["id"]

    if ignored_unauth:
        log.warning("%d message(s) d'un expéditeur NON autorisé ignoré(s).", ignored_unauth)

    if not chosen:
        log.info("Aucune commande exploitable dans ce lot.")
        return 0

    kind, days = chosen
    if kind == "aide":
        _send(token, chosen_chat, HELP_TEXT)
        return 0

    # kind == "maj"
    _send(token, chosen_chat,
          f"⏳ Rejeu des <b>{days}</b> dernier(s) jour(s) lancé — ça arrive sur le canal…")
    log.info("Commande /maj %d de l'utilisateur autorisé → rejeu.", days)
    rc = run_replay(
        config_path,
        days=days,
        max_per_account=DEFAULT_MAX_PER_ACCOUNT,
        max_per_day=DEFAULT_MAX_PER_DAY,
        max_pages=DEFAULT_MAX_PAGES,
        dry_run=False,
        sleep_between=3.0,
    )
    _send(token, chosen_chat,
          "✅ Rejeu terminé." if rc == 0
          else "⚠️ Le rejeu a rencontré un souci — regarde les logs GitHub Actions.")
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description="Écouteur de commandes Telegram (poll).")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--setup-menu", action="store_true",
                        help="Publie seulement le menu de commandes du bot, puis sort.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    try:
        if args.setup_menu:
            settings = load_settings(args.config)
            if not settings.telegram_bot_token:
                log.error("TELEGRAM_BOT_TOKEN absent.")
                return 1
            _publish_menu(settings.telegram_bot_token)
            log.info("Menu de commandes publié.")
            return 0
        return run_listener(args.config)
    except Exception as exc:  # noqa: BLE001
        log.error("Échec de l'écouteur : %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
