"""Le Radar iA en un seul message : grands titres sur Telegram + journal mis en page sur le site.

Demande de Hugo (17/11/2026) : trop de messages par jour. Le canal reçoit
désormais UN message texte (titres du jour + bouton « Lire le journal ») ;
le digest complet (essentiel + « Pour aller plus loin » + sources) est publié
comme page web : https://hl-consulting.tech/knowledge-hub/veille-ia/journal/AAAA-MM-JJ/

Le digest reste produit au même format HTML Telegram (le podcast le lit tel quel) ;
ce module le transforme en titres et en page.
"""
from __future__ import annotations

from datetime import date
from html import escape, unescape
import json
from pathlib import Path
import re

SITE = "https://hl-consulting.tech"
JOURNAL_PATH = "/knowledge-hub/veille-ia/journal/"
DAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
          "septembre", "octobre", "novembre", "décembre")
SKIP_TITLES = ("l'essentiel du jour", "l’essentiel du jour", "la phrase du jour", "veille ia")
TAG = re.compile(r"<[^>]+>")


def long_date(day: date) -> str:
    return f"{DAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]} {day.year}"


def journal_url(day: date) -> str:
    return f"{SITE}{JOURNAL_PATH}{day.isoformat()}/"


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(TAG.sub("", html))).strip()


def _without_details(digest: str) -> str:
    return re.sub(r"<blockquote[^>]*>.*?</blockquote>", "", digest, flags=re.S)


def headlines(digest: str) -> list[str]:
    """Titres de section (lignes qui commencent par un titre en gras), hors rubriques fixes."""
    titles = []
    for line in _without_details(digest).splitlines():
        m = re.match(r"\s*(\S{0,3}\s*)<b>(.*?)</b>(.*)$", line)
        if not m:
            continue
        rest = _text(m.group(3))
        if rest and len(rest) > 3:  # gras au milieu d'un paragraphe : pas un titre
            continue
        title = _text(m.group(1) + m.group(2)).strip(" :—-")
        if title and not any(s in title.lower() for s in SKIP_TITLES):
            titles.append(title)
    return titles


def is_calm_day(digest: str) -> bool:
    return not headlines(digest)


def teaser(digest: str, day: date) -> tuple[str, dict]:
    """Message Telegram unique + bouton vers le journal du jour."""
    titles = headlines(digest)
    head = f"<b>🗞️ Le Radar iA — {long_date(day)}</b>"
    if not titles:  # journée calme : on garde le petit mot tel quel
        return f"{head}\n\n{digest.strip()}", {}
    lines = "\n".join(f"• {escape(t, quote=False)}" for t in titles)
    text = (f"{head}\n\n{lines}\n\n"
            f"📰 Tout le détail, mis en page, dans <a href=\"{journal_url(day)}\">le journal du jour</a>.")
    markup = {"inline_keyboard": [[{"text": "📰 Lire le journal", "url": journal_url(day)}]]}
    return text, markup


# ── Page web ─────────────────────────────────────────────────────────────────
def _paragraph(html: str) -> str:
    html = html.strip().replace("\n", "<br>\n")
    return f"<p>{html}</p>" if html else ""


def body_html(digest: str) -> str:
    """HTML Telegram (b, i, a, blockquote expandable, puces •) → HTML de page."""
    parts = re.split(r"(<blockquote[^>]*>.*?</blockquote>)", digest, flags=re.S)
    out = []
    for part in parts:
        if part.startswith("<blockquote"):
            inner = re.sub(r"^<blockquote[^>]*>|</blockquote>$", "", part, flags=re.S).strip()
            inner = re.sub(r"^🔎\s*<b>Pour aller plus loin\s*[—–-]?\s*</b>\s*", "", inner)
            out.append('<details class="jr-more"><summary>Pour aller plus loin</summary>'
                       f'<div class="jr-more__body">{_paragraph(inner)}</div></details>')
            continue
        for block in re.split(r"\n\s*\n", part):
            lines = [l for l in block.strip().splitlines() if l.strip()]
            while lines:
                first = lines[0]
                m = re.match(r"\s*(\S{0,3}\s*)<b>(.*?)</b>\s*$", first)
                if m:
                    title = _text(m.group(1) + m.group(2))
                    lower = title.lower()
                    if "essentiel du jour" in lower or lower.startswith("🤖 veille ia"):
                        lines.pop(0)
                        continue
                    if "phrase du jour" in lower:
                        attrs = ' class="jr-quote-title"'
                    else:
                        n = sum(1 for o in out if o.startswith('<h2 id="s')) + 1
                        attrs = f' id="s{n}"'
                    out.append(f"<h2{attrs}>{(m.group(1).strip() + ' ' + m.group(2)).strip()}</h2>")
                    lines.pop(0)
                    continue
                break
            if lines:
                out.append(_paragraph("\n".join(lines)))
    return "\n".join(o for o in out if o)


CSS = """
.jr{padding-block:var(--space-12) var(--space-24);}
.jr-head{border-bottom:2px solid var(--text); padding-bottom:var(--space-6); margin-bottom:var(--space-8);}
.jr-head h1{font-family:var(--font-display); font-size:clamp(2.4rem,7vw,4.2rem); line-height:.95; margin:var(--space-2) 0 var(--space-3);}
.jr-head h1 em{font-style:normal; color:var(--c-violet); text-transform:none;}
.jr-date{font-family:var(--font-mono); font-size:.85rem; text-transform:uppercase; letter-spacing:.08em; color:var(--text-muted);}
.jr-toc{list-style:none; padding:0; margin:var(--space-6) 0 0; display:grid; gap:var(--space-2);}
.jr-toc a{text-decoration:none; font-weight:600; color:var(--text);}
.jr-toc a:hover{color:var(--link-hover);}
.jr-body{max-width:var(--prose-max); font-size:1.06rem; line-height:1.65;}
.jr-body h2{text-transform:none; scroll-margin-top:90px; font-family:var(--font-display); font-size:clamp(1.35rem,3.6vw,1.75rem); line-height:1.15; margin:var(--space-12) 0 var(--space-3); padding-top:var(--space-6); border-top:1px solid var(--border);}
.jr-body h2:first-child{margin-top:0; border-top:0; padding-top:0;}
.jr-body p{margin:0 0 var(--space-4);}
.jr-more{margin:0 0 var(--space-6); border:1px solid var(--border); border-left:4px solid var(--c-violet); border-radius:var(--radius); background:var(--surface);}
.jr-more summary{cursor:pointer; padding:var(--space-3) var(--space-4); font-weight:700; font-size:.95rem;}
.jr-more__body{padding:0 var(--space-4) var(--space-2); font-size:.98rem;}
.jr-quote-title + p{font-family:var(--font-display); font-size:1.3rem; line-height:1.35;}
.jr-listen{margin:0 0 var(--space-12); padding:var(--space-6); border:2px solid var(--text); border-radius:var(--radius); background:var(--surface-alt); scroll-margin-top:90px;}
.jr-listen a{font-weight:700;}
.jr-player{margin:var(--space-3) 0;}
.jr-player p{margin:0 0 var(--space-2);}
.jr-player audio{width:100%;}
.jr-follow{margin:var(--space-4) 0 0; font-size:.92rem;}
.jr-nav{display:flex; justify-content:space-between; gap:var(--space-4); margin-top:var(--space-8); font-weight:600;}
"""


def page_html(digest: str, day: date, *, prev_day: str | None = None, next_day: str | None = None) -> str:
    url = journal_url(day)
    titles = headlines(digest)
    title = f"Le Radar iA du {day.day} {MONTHS[day.month - 1]} {day.year}"
    desc = ("Veille IA du jour, en français : " + " · ".join(titles))[:300] if titles else \
        "Veille IA du jour, en français."
    toc = "".join(f'<li><a href="#s{i}">{escape(t)}</a></li>' for i, t in enumerate(titles, 1))
    nav = ""
    if prev_day or next_day:
        prev = f'<a href="{JOURNAL_PATH}{prev_day}/">← {prev_day}</a>' if prev_day else "<span></span>"
        nxt = f'<a href="{JOURNAL_PATH}{next_day}/">{next_day} →</a>' if next_day else "<span></span>"
        nav = f'<nav class="jr-nav" aria-label="Autres jours">{prev}{nxt}</nav>'
    ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": title, "description": desc,
          "datePublished": day.isoformat(), "inLanguage": "fr-FR", "url": url,
          "author": {"@type": "Person", "@id": f"{SITE}/#hugo", "name": "Hugo Lahutte"},
          "isPartOf": {"@type": "CollectionPage", "url": f"{SITE}/knowledge-hub/veille-ia/"}}
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)} · Knowledge Hub</title>
<meta name="description" content="{escape(desc)}">
<link rel="canonical" href="{url}">
<link rel="alternate" hreflang="fr" href="{url}">
<link rel="alternate" hreflang="x-default" href="{url}">
<meta name="author" content="Hugo Lahutte">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta property="og:type" content="article">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="fr_FR">
<meta property="og:image" content="{SITE}/assets/podcast/art/show-cover-{day:%Y-%m}.jpg">
<link rel="preconnect" href="https://api.fontshare.com" crossorigin>
<link href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,900&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;800;900&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="icon" href="/knowledge-hub/favicon.ico" sizes="any">
<link rel="icon" href="/knowledge-hub/favicon.svg" type="image/svg+xml">
<meta name="theme-color" content="#FFFCF8">
<script>(function(){{try{{var t=localStorage.getItem("kh-theme");if(t==="dark"||t==="light")document.documentElement.setAttribute("data-theme",t);}}catch(e){{}}}})();</script>
<link rel="stylesheet" href="/knowledge-hub/style.css?v=20260622a">
<style>{CSS}</style>
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
</head>
<body>
<a class="skip-link" href="#main">Aller au contenu</a>
<header class="nav">
  <span class="nav__brand"><a class="nav__crumb-home" href="/">HL Consulting</a><span class="nav__crumb-sep" aria-hidden="true">›</span><a class="nav__wordmark" href="/knowledge-hub/"><b>KNOWLEDGE</b> <span>HUB</span></a></span>
  <nav aria-label="Principale"><ul class="nav__links"><li><a href="/knowledge-hub/immersion-ia/">Le Kiosque iA</a></li><li><a href="/knowledge-hub/veille-ia/">Archive de la veille</a></li></ul></nav>
</header>
<main id="main" class="container jr">
  <header class="jr-head">
    <p class="kicker">Le Radar iA · le journal du jour</p>
    <h1>Le Radar <em>iA</em></h1>
    <p class="jr-date">{long_date(day)}</p>
    <ul class="jr-toc">{toc}</ul>
  </header>
  <section id="ecouter" class="jr-listen" aria-label="Écouter">
    <p class="kicker">Le Podcast iA du jour</p>
    <div class="jr-player"><p><b>⚡ Le Flash</b> · l'essentiel en deux minutes</p>
      <audio controls preload="none" src="/assets/podcast/archive/{day.isoformat()}/short.mp3"></audio></div>
    <div class="jr-player"><p><b>🎧 Le Débrief</b> · la veille en détail</p>
      <audio controls preload="none" src="/assets/podcast/archive/{day.isoformat()}/full.mp3"></audio></div>
    <p class="jr-follow">Aussi sur <a href="https://open.spotify.com/show/10f9eIN4y5iCxx0hc17FUK">Spotify</a> · <a href="https://podcasts.apple.com/us/podcast/le-podcast-ia/id6823971009?l=fr">Apple Podcasts</a> · chaque matin sur <a href="https://t.me/VeilleIA_HL">Telegram</a>.</p>
  </section>
  <article class="jr-body">
{body_html(digest)}
  </article>
  {nav}
</main>
<footer class="footer"><div class="container"><p class="caption">Hugo Lahutte · Le Radar iA · © {day.year}</p></div></footer>
<script src="/knowledge-hub/theme.js?v=20260601d" defer></script>
</body>
</html>
"""


def save(digest: str, day: date, folder: str | Path = "journal") -> Path:
    """Sauvegarde le digest du jour (source de la page, poussée vers le site)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{day.isoformat()}.json"
    path.write_text(json.dumps({"date": day.isoformat(), "headlines": headlines(digest), "digest": digest},
                               ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_site(source: str | Path, site_root: str | Path) -> list[Path]:
    """Écrit toutes les pages journal/AAAA-MM-JJ/index.html (avec navigation) dans le site."""
    entries = sorted(Path(source).glob("*.json"))
    dates = [p.stem for p in entries]
    written = []
    for i, path in enumerate(entries):
        data = json.loads(path.read_text(encoding="utf-8"))
        day = date.fromisoformat(data["date"])
        html = page_html(data["digest"], day, prev_day=dates[i - 1] if i else None,
                         next_day=dates[i + 1] if i + 1 < len(dates) else None)
        dest = Path(site_root) / "knowledge-hub/veille-ia/journal" / day.isoformat() / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or dest.read_text(encoding="utf-8") != html:
            dest.write_text(html, encoding="utf-8")
            written.append(dest)
    return written


if __name__ == "__main__":
    import sys
    for p in build_site(sys.argv[1], sys.argv[2]):
        print("Page journal :", p)


def sections(digest: str) -> list[dict]:
    """Sujets du jour pour les pages-images : titre + texte essentiel (sans « Pour aller plus loin »)."""
    html = body_html(digest)
    out, current = [], None
    for m in re.finditer(r'<h2(?P<attrs>[^>]*)>(?P<title>.*?)</h2>|<p>(?P<p>.*?)</p>|<details.*?</details>', html, re.S):
        if m.group("title") is not None:
            current = {"title": m.group("title"), "quote": "jr-quote-title" in m.group("attrs"), "paragraphs": []}
            out.append(current)
        elif m.group("p") is not None:
            if current is None:
                current = {"title": "", "quote": False, "paragraphs": []}
                out.append(current)
            current["paragraphs"].append(m.group("p"))
    return [s for s in out if s["title"] or s["paragraphs"]]
