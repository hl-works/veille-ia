"""Le Radar iA en pages-images (format téléphone 1080 × 1920) pour Telegram.

Choix de Hugo (17/11/2026) : le journal du jour part dans Telegram sous forme de
quelques pages lisibles sur téléphone, en un seul envoi (album) — une avec
iAstro, les sujets, puis la phrase du jour signée Hugo. Le détail complet et les
sources restent sur la page web du jour.

Rendu Chromium (Playwright). La pagination est faite dans le navigateur : on
remplit chaque page jusqu'à ce qu'elle déborde ; un sujet trop long seul sur sa
page voit sa taille de texte réduite.
"""
from __future__ import annotations

import base64
from datetime import date
from html import escape
from pathlib import Path

from .journal import MONTHS, DAYS, headlines, sections

W, H = 1080, 1920
MAX_PAGES = 10  # limite d'un album Telegram


def _data_uri(path: Path | None) -> str:
    if not path or not Path(path).is_file():
        return ""
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


CSS = """
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@700;800;900&family=Inter:wght@400;600;700&family=IBM+Plex+Mono:wght@500&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
body{background:#222;font-family:Inter,'Liberation Sans',Arial,sans-serif;color:#0c0c0c}
.page{width:1080px;height:1920px;background:#FFFCF8;position:relative;overflow:hidden;margin:0 0 20px;display:flex;flex-direction:column}
.bar{height:118px;display:flex;align-items:center;justify-content:space-between;padding:0 64px;border-bottom:4px solid #0c0c0c;flex:none}
.brand{font-family:Archivo,'Liberation Sans',sans-serif;font-weight:900;font-size:52px;letter-spacing:-.5px}
.brand em{font-style:normal;color:#39359E}
.folio{font-family:'IBM Plex Mono',monospace;font-size:28px;color:#555}
.content{flex:1;padding:56px 64px 0;overflow:hidden;display:flex;flex-direction:column;gap:40px}
.foot{height:96px;flex:none;border-top:4px solid #0c0c0c;display:flex;align-items:center;justify-content:space-between;padding:0 64px;font-family:'IBM Plex Mono',monospace;font-size:26px;color:#333}
.foot b{color:#39359E}
/* une */
.une .content{padding-top:40px;gap:28px}
.kicker{font-family:'IBM Plex Mono',monospace;font-size:28px;letter-spacing:3px;text-transform:uppercase;color:#C6121F}
.une h1{font-family:Archivo,'Liberation Sans',sans-serif;font-weight:900;font-size:150px;line-height:.86;letter-spacing:-3px}
.une h1 em{font-style:normal;color:#39359E}
.date{font-family:Archivo,'Liberation Sans',sans-serif;font-weight:800;font-size:44px;text-transform:uppercase}
.hero{display:flex;gap:34px;align-items:flex-end}
.hero img{width:430px;height:430px;object-fit:cover;border:4px solid #0c0c0c;border-radius:28px;flex:none}
.hero .bubble{font-size:36px;line-height:1.3;font-weight:600;background:#fff;border:4px solid #0c0c0c;border-radius:28px;padding:26px 30px;margin-bottom:40px}
.toc{list-style:none;display:flex;flex-direction:column;gap:20px;counter-reset:n}
.toc li{counter-increment:n;display:flex;gap:22px;font-size:38px;line-height:1.22;font-weight:700}
.toc li:before{content:counter(n,decimal-leading-zero);font-family:'IBM Plex Mono',monospace;color:#C6121F;font-size:32px;padding-top:6px;flex:none}
/* sujets */
.topic{border-top:3px solid #0c0c0c;padding-top:30px}
.topic:first-child{border-top:0;padding-top:0}
.num{font-family:'IBM Plex Mono',monospace;font-size:28px;color:#C6121F;letter-spacing:2px;margin-bottom:12px}
.topic h2{font-family:Archivo,'Liberation Sans',sans-serif;font-weight:800;font-size:54px;line-height:1.08;letter-spacing:-.5px;margin-bottom:22px}
.topic p{font-size:37px;line-height:1.42;margin-bottom:16px}
.topic p b{font-weight:700}
.topic a{color:#39359E;text-decoration:none;font-weight:600}
.more{font-family:'IBM Plex Mono',monospace;font-size:26px;color:#39359E}
/* fin */
.quote{background:#0c0c0c;color:#FFFCF8;border-radius:28px;padding:56px 56px 50px}
.quote .kicker{color:#E8B730}
.quote p{font-family:Archivo,'Liberation Sans',sans-serif;font-weight:800;font-size:56px;line-height:1.16;margin-top:22px}
.sign{display:flex;flex-direction:column;align-items:flex-start;gap:26px;margin-top:10px}
.sign img{width:520px;height:520px;object-fit:cover;border-radius:28px;border:4px solid #0c0c0c;flex:none}
.sign .who{font-family:Archivo,'Liberation Sans',sans-serif;font-weight:900;font-size:58px;line-height:1}
.sign .role{font-size:32px;color:#444;margin-top:12px;line-height:1.3}
.cta{border:4px solid #0c0c0c;border-radius:28px;padding:34px 40px;font-size:36px;line-height:1.35;font-weight:600}
.cta b{color:#39359E}
"""

JS = """
(() => {
  const H = 1920;
  const pool = document.getElementById('pool');
  const blocks = [...pool.children];
  const book = document.getElementById('book');
  const total = () => book.querySelectorAll('.page').length;
  function newPage() {
    const p = document.createElement('section');
    p.className = 'page';
    p.innerHTML = document.getElementById('tpl').innerHTML;
    book.appendChild(p);
    return p;
  }
  let page = null;
  for (const b of blocks) {
    if (b.classList.contains('break') || !page) { page = newPage(); }
    const c = page.querySelector('.content');
    c.appendChild(b);
    if (c.scrollHeight > c.clientHeight + 1) {
      if (c.children.length > 1) {
        c.removeChild(b);
        page = newPage();
        page.querySelector('.content').appendChild(b);
      }
      const c2 = page.querySelector('.content');
      let size = 37;
      while (c2.scrollHeight > c2.clientHeight + 1 && size > 26) {
        size -= 1;
        b.querySelectorAll('p').forEach(p => p.style.fontSize = size + 'px');
      }
    }
  }
  // Pages de sujets peu remplies : on agrandit le texte (plus lisible, moins de blanc).
  for (const pg of book.querySelectorAll('.page:not(.une)')) {
    const c = pg.querySelector('.content');
    const ps = c.querySelectorAll('.topic p:not(.num)');
    const hs = c.querySelectorAll('.topic h2');
    if (!ps.length) continue;
    let size = parseFloat(getComputedStyle(ps[0]).fontSize);
    while (size < 48 && c.scrollHeight <= c.clientHeight) {
      size += 1;
      ps.forEach(p => p.style.fontSize = size + 'px');
      hs.forEach(h => h.style.fontSize = Math.round(size * 1.5) + 'px');
    }
    if (c.scrollHeight > c.clientHeight) {
      size -= 1;
      ps.forEach(p => p.style.fontSize = size + 'px');
      hs.forEach(h => h.style.fontSize = Math.round(size * 1.5) + 'px');
    }
  }
  const pages = [...book.querySelectorAll('.page')];
  pages.forEach((p, i) => { const f = p.querySelector('.folio'); if (f) f.textContent = `${i + 1} / ${pages.length}`; });
  window.__pages = pages.length;
})();
"""


def build_html(digest: str, day: date, portrait: Path | None = None, signature: Path | None = None,
               url: str = "") -> str:
    secs = sections(digest)
    topics = [s for s in secs if s["title"] and not s["quote"]]
    quote = next((s for s in secs if s["quote"]), None)
    date_txt = f"{DAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]} {day.year}"
    bar = ('<div class="bar"><span class="brand">LE RADAR <em>iA</em></span>'
           '<span class="folio"></span></div>')
    foot = ('<div class="foot"><span>Le détail et les sources : <b>hl-consulting.tech</b></span>'
            '<span>iAstro × Hugo</span></div>')
    pic = _data_uri(portrait)
    hero = (f'<div class="hero">{f"<img src={chr(34)}{pic}{chr(34)} alt=\"\">" if pic else ""}'
            f'<div class="bubble">Salut ! Voilà ce qu\'il faut retenir de l\'IA ce matin 👇</div></div>')
    toc = "".join(f"<li>{escape(t)}</li>" for t in headlines(digest)[:7])
    une = (f'<section class="page une">{bar}<div class="content">'
           f'<p class="kicker">Le journal du matin</p><h1>LE RADAR<br><em>iA</em></h1>'
           f'<p class="date">{date_txt}</p>{hero}<ol class="toc">{toc}</ol></div>{foot}</section>')
    blocks = []
    for i, t in enumerate(topics, 1):
        paras = "".join(f"<p>{p}</p>" for p in t["paragraphs"])
        blocks.append(f'<article class="topic"><p class="num">SUJET {i:02d} / {len(topics):02d}</p>'
                      f'<h2>{t["title"]}</h2>{paras}</article>')
    sig = _data_uri(signature)
    end = '<div class="break"></div>' if False else ""
    closing = []
    if quote and quote["paragraphs"]:
        closing.append(f'<div class="quote"><p class="kicker">✨ La phrase du jour</p><p>{quote["paragraphs"][0]}</p></div>')
    closing.append('<div class="cta">🎧 La version audio est juste en dessous : <b>Le Débrief</b>, et <b>Le Flash</b> '
                   'en deux minutes sur la page du jour.</div>')
    closing.append(f'<div class="sign">{f"<img src={chr(34)}{sig}{chr(34)} alt=\"\">" if sig else ""}'
                   '<div><p class="who">Hugo LaHutte</p><p class="role">avec iAstro · Le Radar iA, '
                   'chaque matin sur Telegram</p></div></div>')
    pool = "".join(blocks) + "".join(closing)
    tpl = f'{bar}<div class="content"></div>{foot}'
    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
            f'<div id="book">{une}</div><template id="tpl">{tpl}</template>'
            f'<div id="pool" style="display:none">{pool}</div>{end}</body></html>')


def render(digest: str, day: date, out_dir: Path, *, portrait: Path | None = None,
           signature: Path | None = None) -> list[Path]:
    from playwright.sync_api import sync_playwright
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    html = build_html(digest, day, portrait, signature)
    # Les blocs « break » forcent une nouvelle page ; JS les gère à l'insertion.
    html = html.replace('<div class="break"></div>', '<div class="break" style="display:none"></div>')
    (out_dir / "radar.html").write_text(html, encoding="utf-8")
    paths = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        page.goto((out_dir / "radar.html").resolve().as_uri())
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        # Pool visible pour mesurer, puis pagination.
        page.evaluate("document.getElementById('pool').style.display='block'")
        page.evaluate(JS)
        pages = page.query_selector_all(".page")
        if len(pages) > MAX_PAGES:
            raise RuntimeError(f"{len(pages)} pages : trop pour un album Telegram")
        for i, el in enumerate(pages, 1):
            path = out_dir / f"radar-{i:02d}.png"
            el.screenshot(path=str(path))
            paths.append(path)
        browser.close()
    return paths
