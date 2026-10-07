"""Habillage sonore du podcast : jingles d'intro, transitions, outro.

Généré avec ElevenLabs Music (POST /v1/music, instrumental) — nécessite l'accès
« Musique » sur la clé ELEVENLABS_API_KEY. Lancé via le casting
(`.state/casting` avec une clé "habillage"), résultat poussé sur la branche
`ecoute` : rien n'est publié. Pour chaque style, une démo « en situation »
(intro → voix → transition → voix → outro) est assemblée pour juger à l'oreille.

params["habillage"] = {"styles": [{"nom": "...", "ambiance": "..."}],
                       "voix_texte": ["phrase 1", "phrase 2"]}
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import requests

from .elevenlabs_tts import API, ElevenLabsError, ElevenLabsTTS, _key

# Brief sonore d'Hugo (07/10/2026) : moderne, basse ronde et pleine, rendu hi-fi
# propre, pas de musique d'ascenseur.
BRIEF = ('instrumental only, no vocals, modern and premium, round full warm bass, punchy but '
         'clean kick, crisp high-fidelity mix with wide stereo and real dynamics, confident and '
         'upbeat, made for a French tech and AI news podcast')

PIECES = [  # (rôle, durée en secondes, consigne)
    ('intro', 8, 'podcast opening jingle, catchy signature motif, builds quickly then ends on a clean hit'),
    ('transition', 3, 'very short transition stinger between two news topics, one musical gesture, clean ending'),
    ('outro', 6, 'podcast closing jingle reusing the opening motif, warm resolved ending'),
]


def compose(prompt: str, seconds: float, dest: Path) -> None:
    r = requests.post(f'{API}/v1/music', params={'output_format': 'mp3_44100_128'},
                      headers={'xi-api-key': _key(), 'accept': 'audio/mpeg'},
                      json={'prompt': prompt, 'music_length_ms': int(max(3, seconds) * 1000),
                            'force_instrumental': True}, timeout=(10, 300))
    if not (r.ok and r.content):
        raise ElevenLabsError(r.status_code, r.text)
    dest.write_bytes(r.content)


def _ffmpeg(*args: str) -> None:
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', *args], check=True, timeout=300,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def demo(intro: Path, transition: Path, outro: Path, voix: list[Path], dest: Path) -> None:
    """intro → voix 1 → transition → voix 2 → outro, musique à -3 dB, fondus courts."""
    inputs = [intro, voix[0], transition, voix[1] if len(voix) > 1 else voix[0], outro]
    args: list[str] = []
    for f in inputs:
        args += ['-i', str(f)]
    music = '[{i}:a]aformat=sample_rates=44100:channel_layouts=mono,volume=0.7,afade=t=out:st=0:d=0.01[m{i}]'
    labels = []
    chains = []
    for i in range(5):
        if i in (0, 2, 4):
            chains.append(music.format(i=i))
            labels.append(f'[m{i}]')
        else:
            chains.append(f'[{i}:a]aformat=sample_rates=44100:channel_layouts=mono[v{i}]')
            labels.append(f'[v{i}]')
    graph = ';'.join(chains) + ';' + ''.join(labels) + 'concat=n=5:v=0:a=1,loudnorm=I=-16:TP=-1.5:LRA=11[out]'
    _ffmpeg(*args, '-filter_complex', graph, '-map', '[out]', '-ac', '1', '-ar', '44100',
            '-codec:a', 'libmp3lame', '-b:a', '128k', str(dest))


UNIVERS_BRIEF = ('instrumental only, no vocals, round full warm bass, crisp high-fidelity mix, '
                 'wide stereo, real dynamics, polished modern production')


def run_univers(spec: dict, out: Path) -> list[dict]:
    """Planche d'univers : un extrait musical seul par style (pas de voix), pour
    qu'Hugo choisisse une direction avant de composer les jingles."""
    secs = float(spec.get('duree_s', 15))
    results: list[dict] = []
    for n, u in enumerate(spec['univers'], 1):
        nom = u.get('nom') or f'univers-{n}'
        row = {'style': nom, 'ambiance': u.get('ambiance', '')}
        f = out / f'{n:02d}-{nom}.mp3'
        try:
            compose(f"{u.get('ambiance', '')}. {UNIVERS_BRIEF}.", secs, f)
            row['demo'] = f.name
        except (ElevenLabsError, RuntimeError) as exc:
            row['erreur'] = str(exc)[:300]
        results.append(row)
    return results


def run(params: dict, out: Path, voice_cfg: dict) -> list[dict]:
    spec = params.get('habillage') or {}
    if spec.get('univers'):
        out.mkdir(parents=True, exist_ok=True)
        results = run_univers(spec, out)
        lines = ['# Univers sonores — extraits', '', '| # | Univers | Fichier | Erreur |', '|---|---|---|---|']
        for n, r in enumerate(results, 1):
            lines.append(f"| {n} | {r['style']} — {r['ambiance']} | {r.get('demo', '')} | {r.get('erreur', '')} |")
        (out / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return results
    styles = spec.get('styles') or []
    phrases = spec.get('voix_texte') or [
        "Bonjour et bienvenue dans votre veille IA du jour.",
        "Côté OpenAI, maintenant. Une annonce qui va compter pour les entreprises."]
    out.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        voix: list[Path] = []
        for i, phrase in enumerate(phrases[:2]):
            script = Path(tmp) / f'v{i}.txt'
            script.write_text(phrase, encoding='utf-8')
            dest = Path(tmp) / f'v{i}.mp3'
            ElevenLabsTTS(voice_cfg).synthesize(script, dest)
            voix.append(dest)
        for n, style in enumerate(styles, 1):
            nom = style.get('nom') or f'style-{n}'
            row = {'style': nom, 'ambiance': style.get('ambiance', ''), 'fichiers': []}
            try:
                files = {}
                for role, secs, consigne in PIECES:
                    f = out / f'{n:02d}-{nom}-{role}.mp3'
                    compose(f"{consigne}. Style: {style.get('ambiance', '')}. {BRIEF}.", secs, f)
                    files[role] = f
                    row['fichiers'].append(f.name)
                d = out / f'{n:02d}-{nom}-DEMO.mp3'
                demo(files['intro'], files['transition'], files['outro'], voix, d)
                row['demo'] = d.name
            except (ElevenLabsError, RuntimeError, subprocess.CalledProcessError) as exc:
                row['erreur'] = str(exc)[:300]
            results.append(row)
    lines = ['# Habillage sonore — propositions', '', '| # | Style | Démo | Erreur |', '|---|---|---|---|']
    for n, r in enumerate(results, 1):
        lines.append(f"| {n} | {r['style']} — {r['ambiance']} | {r.get('demo', '')} | {r.get('erreur', '')} |")
    (out / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (out / 'habillage.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return results
