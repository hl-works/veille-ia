"""Fabrique automatiquement le numéro iAstro Sunday de la semaine.

Autorisation permanente de Hugo (17 novembre 2026) : le numéro est fabriqué et
publié chaque dimanche sans validation préalable.

Étapes :
1. Candidats = items de feed.json de la semaine ISO (lundi → dimanche).
2. Claude (+ recherche web) choisit 4 actus, vérifie chacune sur une source
   primaire, écrit le scénario (4 histoires × 6 cases) au format des numéros
   publiés. Seuls Hugo et iAstro apparaissent (pas de personnalité réelle).
3. GPT Image (OpenAI) dessine 4 planches 3×2 + 1 couverture à partir des
   références de personnages et de la tenue du mois.
4. Écrit l'épisode + l'art dans le checkout du site ; la publication (build,
   commit, push) est faite par le workflow.

Usage : python scripts/iastro-weekly.py --site PATH [--feed feed.json] [--date AAAA-MM-JJ]
Code de sortie 0 + « SKIP » si le numéro de la semaine existe déjà.
"""
import argparse
import base64
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

import anthropic
import yaml

PARIS = ZoneInfo("Europe/Paris")
IMAGE_MODEL = os.environ.get("IASTRO_IMAGE_MODEL", "gpt-image-2")
IMAGE_QUALITY = os.environ.get("IASTRO_IMAGE_QUALITY", "high")
NEWS_COUNT = 4
APPROVAL_REFERENCE = (
    "Autorisation permanente de Hugo du 17 novembre 2026 : « ça part tout seul le dimanche ». "
    "Numéro fabriqué et publié automatiquement (sélection, sources primaires vérifiées par recherche web, "
    "scénario Claude, dessins GPT Image selon la direction validée), sans relecture préalable."
)
BRANDS = ["openai", "anthropic", "mistral", "google", "elevenlabs", "shop", "meta", "perplexity"]
MONTHS = ["", "janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
          "septembre", "octobre", "novembre", "decembre"]
CROPS = [{"x": c / 3, "y": r / 2, "w": 1 / 3, "h": 0.5} for r in range(2) for c in range(3)]

STYLE = (
    "Use case: illustration-story. Produce ONE original full-color comic master image, landscape 3:2 ratio, "
    "EXACTLY SIX equally sized panels in a rigid 3 columns × 2 rows grid, thin black panel borders at exactly "
    "thirds and half. No outer title band, no page margin. Every panel fills its cell, independently cropped later "
    "for mobile. NO LETTERS, NO TEXT, NO SPEECH BUBBLES, NO CAPTIONS, NO LOGOS. References: first image fixes both "
    "characters' faces and proportions; second fixes this month's clothing only. Match the original expressive "
    "manga ink-and-watercolor comic style, varied line weights and lively acting. {outfits} Keep head axes "
    "generally upright, vary profile, front, three-quarter, wide shots and closeups; expressive big open mouths, "
    "eyebrows, gestures. Hugo generally left, iAstro right. {setting} Maintain clear anatomy, only these two "
    "recurring people, no real public figures. Preserve exact identity and outfits across all six panels. "
    "Story: {story} SIX PANELS IN ORDER: {panels} This is an imaginary metaphor, NOT documentation of a real product."
)


def week(today):
    monday = today - dt.timedelta(days=today.weekday())
    y, w, _ = monday.isocalendar()
    return f"{y}-W{w:02d}", monday, monday + dt.timedelta(days=6)


def candidates(feed, monday, sunday, limit=30):
    items = [i for i in feed if monday.isoformat() <= i.get("date", "") <= sunday.isoformat()]
    items.sort(key=lambda i: -i.get("score", 0))
    return [{k: i.get(k) for k in ("date", "titre_fr", "resume_fr", "tweet_url", "auteur_x", "score")}
            for i in items[:limit]]


def system_prompt(site):
    comics = site / "knowledge-hub/comics"
    docs = "\n\n".join((comics / p).read_text() for p in ("AGENTS.md", "kit/docs/BIBLE.md"))
    example = json.loads((comics / "episodes/2026-W42.json").read_text())
    example_art = json.loads((comics / "art/2026-W42/production.json").read_text())
    return (
        "Tu fabriques le numéro hebdomadaire d'« iAstro Sunday », la BD du dimanche de Hugo Lahutte "
        "(best of de l'actu IA de la semaine, lecture sur téléphone). Hugo a donné une autorisation permanente : "
        "le numéro est publié sans relecture, donc la rigueur factuelle repose entièrement sur toi.\n\n"
        "## Règles de la série (extraits du dépôt)\n" + docs +
        "\n\n## Numéro de référence publié (W42) — reproduis ce ton, ce format et cette qualité\n" +
        json.dumps(example, ensure_ascii=False) +
        "\n\n## Prompts d'illustration de W42 (pour voir comment chaque case est décrite)\n" +
        json.dumps([a["prompt"].split("SIX PANELS IN ORDER:")[1] for a in example_art["art"]], ensure_ascii=False)
    )


def user_prompt(issue, monday, sunday, items, month):
    return f"""Numéro {issue} : semaine du {monday:%d/%m/%Y} au {sunday:%d/%m/%Y}. Tenue du mois : {month}.

Candidats issus de la veille (tweets d'annonce, triés par score) :
{json.dumps(items, ensure_ascii=False, indent=1)}

Travail :
1. Choisis EXACTEMENT {NEWS_COUNT} grandes annonces de la semaine, variées (pas deux fois la même entreprise si possible), compréhensibles par un public large. Uniquement des annonces dont l'entreprise a un logo disponible : brand_id parmi {BRANDS} (« shop » = Shopify).
2. Pour CHAQUE annonce, utilise la recherche web pour trouver et lire la source primaire officielle (blog, changelog, communiqué de l'entreprise). Le fait doit être exact, daté et sans chiffre inventé. Si tu ne peux pas vérifier une annonce, remplace-la.
3. Pour chaque annonce, écris une histoire de 6 cases dans l'atelier des possibles, avec une métaphore claire et une chute drôle qui se comprend immédiatement (règles Humour). Hugo et iAstro seulement. Dialogue court (1 ligne par case, speaker « Hugo » côté left ou « Iastro » côté right). Chaque case a une explication factuelle courte.
4. Décris chaque case pour l'illustrateur, en anglais, comme dans les prompts W42 (sans aucun texte dans l'image).

Réponds en terminant par UN SEUL bloc ```json avec exactement cette structure :
{{
 "title": "titre du numéro",
 "reader_description": "une phrase qui présente les quatre histoires",
 "outfits_en": "description anglaise précise des tenues du mois pour Hugo et iAstro (d'après la bible), en reprenant les traits fixes : Hugo adult brown hair short beard teal eyes, dark left-wrist watch, very oversized trousers, cream sneakers ; iAstro child android HUMAN FACE black spiky hair black eyes cyan temple detail and heart on chest, white tunic purple shorts dark tights white-purple boots",
 "setting_en": "décor anglais de saison de l'atelier",
 "cover_en": "description anglaise des objets que tient le duo sur la couverture (un par histoire)",
 "news": [
  {{"id": "slug-court", "brand_id": "...", "model_label": "Produit · précision", "title": "...", "fact": "fait daté et vérifié",
    "intro": {{"title": "...", "summary": "résumé en français simple"}},
    "sources": [{{"url": "source primaire", "publisher": "...", "title": "...", "published_at": "AAAA-MM-JJ"}}],
    "story_en": "une phrase : la métaphore",
    "panels": [ {{"scene_en": "description de la case pour l'illustrateur", "alt": "texte alternatif français",
                  "dialogue": [{{"speaker": "Hugo", "text": "...", "side": "left"}}],
                  "explanation": {{"title": "...", "text": "..."}} }} ]  // exactement 6
  }}
 ]
}}"""


def ask_claude(model, system, user):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=3)
    messages = [{"role": "user", "content": user}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 12}]
    for _ in range(4):  # pause_turn : on relance pour laisser la recherche finir
        resp = client.messages.create(model=model, max_tokens=16000, system=system, messages=messages, tools=tools)
        if resp.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": resp.content}]
    text = "".join(b.text for b in resp.content if b.type == "text")
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if not blocks:
        raise RuntimeError("Claude n'a pas rendu de JSON")
    usage = resp.usage
    print(f"Claude : {usage.input_tokens} tokens entrée / {usage.output_tokens} sortie (dernier tour)")
    return json.loads(blocks[-1])


def check_plan(plan, monday, sunday):
    news = plan["news"]
    assert len(news) == NEWS_COUNT, "Nombre d'actus incorrect"
    assert len({n["id"] for n in news}) == NEWS_COUNT, "Identifiants en double"
    for n in news:
        assert re.fullmatch(r"[a-z0-9-]{2,30}", n["id"]), f"id invalide : {n['id']}"
        assert n["brand_id"] in BRANDS, f"marque sans logo : {n['brand_id']}"
        assert len(n["panels"]) == 6, f"{n['id']} : il faut 6 cases"
        assert n["sources"] and all(s["url"].startswith("https://") for s in n["sources"]), "source manquante"
        for s in n["sources"]:
            published = dt.date.fromisoformat(s["published_at"])
            assert published <= sunday, f"source datée après la semaine : {s['url']}"
            assert not s["url"].startswith(("https://x.com", "https://twitter.com")), "source primaire requise, pas un tweet"
        for p in n["panels"]:
            assert p["scene_en"].strip() and p["alt"].strip() and p["dialogue"], "case incomplète"
            for line in p["dialogue"]:
                assert line["speaker"] in ("Hugo", "Iastro") and line["text"].strip(), "dialogue invalide"
                line["side"] = "left" if line["speaker"] == "Hugo" else "right"


def openai_image(prompt, refs, size, dest):
    boundary = uuid.uuid4().hex
    parts = []
    fields = {"model": IMAGE_MODEL, "prompt": prompt, "size": size, "quality": IMAGE_QUALITY, "n": "1"}
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for ref in refs:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image[]"; filename="{ref.name}"\r\n'
                     f'Content-Type: image/png\r\n\r\n'.encode() + ref.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = Request("https://api.openai.com/v1/images/edits", data=b"".join(parts), headers={
        "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
        "Content-Type": f"multipart/form-data; boundary={boundary}"})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=600) as r:
                data = json.load(r)
            break
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:400]
            if exc.code < 500 and exc.code != 429:
                raise RuntimeError(f"OpenAI images {exc.code} : {detail}") from None
            print(f"OpenAI images {exc.code}, nouvel essai…")
            time.sleep(20 * (attempt + 1))
    else:
        raise RuntimeError("OpenAI images indisponible")
    png = base64.b64decode(data["data"][0]["b64_json"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "Image non PNG"
    dest.write_bytes(png)
    w, h = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    usage = data.get("usage", {})
    print(f"Image {dest.name} : {w}×{h}, {usage.get('total_tokens', '?')} tokens")
    return w, h


def add_to_index(site, issue, period, title):
    """Sitemap + llms.txt, comme pour les numéros publiés à la main."""
    origin = "https://hl-consulting.tech/knowledge-hub/"
    fr, en = f"{origin}comics/{issue}/", f"{origin}en/comics/{issue}/"
    sitemap = site / "knowledge-hub/sitemap.xml"
    xml = sitemap.read_text()
    if fr not in xml:
        links = "".join(f'\n    <xhtml:link rel="alternate" hreflang="{l}" href="{u}"/>'
                        for l, u in (("fr", fr), ("en", en), ("x-default", fr)))
        block = "".join(f"  <url>\n    <loc>{loc}</loc>{links}\n  </url>\n" for loc in (fr, en))
        sitemap.write_text(xml.replace("</urlset>", block + "</urlset>", 1))
    llms = site / "knowledge-hub/llms.txt"
    txt = llms.read_text()
    if fr not in txt:
        period = period.replace("fevrier", "février").replace("aout", "août").replace("decembre", "décembre")
        line = f"- [iAstro Sunday — {period}]({fr}): {title}. Numéro fabriqué automatiquement.\n"
        last = txt.rfind("- [iAstro Sunday")
        end = txt.find("\n", last) + 1 if last >= 0 else len(txt)
        llms.write_text(txt[:end] + "\n" + line + txt[end:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True, type=Path)
    ap.add_argument("--feed", default="feed.json", type=Path)
    ap.add_argument("--date", help="Date de publication (défaut : aujourd'hui à Paris)")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(PARIS).date()
    issue, monday, sunday = week(today)
    comics = args.site / "knowledge-hub/comics"
    episode_path = comics / "episodes" / f"{issue}.json"
    if episode_path.exists():
        print(f"SKIP : {issue} existe déjà.")
        return
    month = sunday.month
    tile = comics / "kit/assets/tiles" / f"month-{month:02d}-{MONTHS[month]}-v1.png"
    refs = [comics / "kit/assets/characters/duo-reference-v2.png", tile]
    assert all(r.exists() for r in refs), "Références de personnages introuvables"

    items = candidates(json.loads(args.feed.read_text()), monday, sunday)
    assert len(items) >= NEWS_COUNT, "Pas assez d'actus dans la veille cette semaine"
    model = yaml.safe_load(Path("config.yaml").read_text()).get("model", "claude-opus-4-8")
    plan = ask_claude(model, system_prompt(args.site), user_prompt(issue, monday, sunday, items, MONTHS[month]))
    check_plan(plan, monday, sunday)

    art_dir = comics / "art" / issue
    art_dir.mkdir(parents=True, exist_ok=True)
    production = {"generated_at": today.isoformat(), "method": f"OpenAI {IMAGE_MODEL} ({IMAGE_QUALITY}), /v1/images/edits",
                  "reference_files": [str(r.relative_to(comics)) for r in refs], "art": []}
    news_out, panels_out = [], []
    for n in plan["news"]:
        prompt = STYLE.format(outfits=plan["outfits_en"], setting=plan["setting_en"], story=n["story_en"],
                              panels=" ".join(f"({i}) {p['scene_en']}" for i, p in enumerate(n["panels"], 1)))
        name = f"{n['id']}-v1.png"
        w, h = openai_image(prompt, refs, "1536x1024", art_dir / name)
        production["art"].append({"file": name, "prompt": prompt, "width": w, "height": h})
        news_out.append({"id": n["id"], "brand_id": n["brand_id"], "model_label": n["model_label"], "title": n["title"],
                         "fact": n["fact"], "intro": n["intro"],
                         "sources": [dict(s, consulted_at=today.isoformat()) for s in n["sources"]]})
        for p, crop in zip(n["panels"], CROPS):
            panels_out.append({"title": n["title"], "image": f"art/{issue}/{name}", "alt": p["alt"],
                               "news_ids": [n["id"]], "dialogue": p["dialogue"], "crop": crop, "layout": "standard",
                               "explanation": p["explanation"]})

    dates = f"{monday.day}–{sunday.day} {MONTHS[sunday.month].upper()} {sunday.year}" if monday.month == sunday.month \
        else f"{monday.day} {MONTHS[monday.month].upper()} – {sunday.day} {MONTHS[sunday.month].upper()} {sunday.year}"
    dates = dates.replace("FEVRIER", "FÉVRIER").replace("AOUT", "AOÛT").replace("DECEMBRE", "DÉCEMBRE")
    cover_prompt = (f"Square original manga comic cover, identity and this month's duo references. {plan['outfits_en']} "
                    f"Hugo left holds a comic sheet and iAstro right presents objects representing the four stories: "
                    f"{plan['cover_en']}. {plan['setting_en']} Clean cream title band: iAstro Sunday; subtitle: "
                    f"Le best of IA en BD; bottom: {dates}. Clear faces and large legible lettering for Telegram, "
                    f"no other text or logos.")
    w, h = openai_image(cover_prompt, refs, "1024x1024", art_dir / "cover-v1.png")
    production["cover"] = {"file": "cover-v1.png", "prompt": cover_prompt, "width": w, "height": h}
    production["authorization"] = APPROVAL_REFERENCE
    production["editorial_cutoff"] = dt.datetime.now(PARIS).isoformat(timespec="minutes")
    (art_dir / "production.json").write_text(json.dumps(production, ensure_ascii=False, indent=2) + "\n")

    episode = {
        "id": issue, "status": "approved", "title": plan["title"],
        "period_start": monday.isoformat(), "period_end": sunday.isoformat(), "publication_date": today.isoformat(),
        "wardrobe_month": month, "format": "webtoon", "reader_variant": "story",
        "approval": {"editorial": True, "art": True, "publish": True, "by": "Hugo", "reference": APPROVAL_REFERENCE},
        "cast_ids": ["hugo", "iastro"], "reader_description": plan["reader_description"],
        "correction_note": f"Numéro fabriqué automatiquement le {today:%d/%m/%Y} ; sélection arrêtée à "
                           f"{dt.datetime.now(PARIS):%H h %M}, heure de Paris.",
        "downloads": {}, "news": news_out, "panels": panels_out, "cover": f"art/{issue}/cover-v1.png",
    }
    episode_path.write_text(json.dumps(episode, ensure_ascii=False, indent=2) + "\n")
    add_to_index(args.site, issue, f"{monday.day} {MONTHS[monday.month]}–{sunday.day} {MONTHS[sunday.month]} {sunday.year}",
                 plan["title"])
    print(f"OK : {issue} prêt — {', '.join(n['id'] for n in news_out)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("STOP:", exc, file=sys.stderr)
        sys.exit(1)
