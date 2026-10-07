"""Casting de voix ElevenLabs : même texte lu par plusieurs voix de France.

Paramètres lus dans un petit JSON (par défaut `.state/casting`) :
    {"genre": "femme", "nombre": 4, "voix_ids": [], "modele": "eleven_v3"}
`voix_ids` vide → sélection automatique (mes voix, puis bibliothèque FR France).

Sortie : un dossier avec un MP3 par voix + README.md récapitulatif. La 1re voix
est aussi générée SANS lexique, pour comparer la prononciation native des marques.
Rien n'est publié : le workflow « Casting voix » pousse ce dossier sur la
branche `ecoute`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

from .audio import apply_lexicon, load_lexicon
from .elevenlabs_tts import (DEFAULT_MODEL, DEFAULT_VOICE_FEMME, ElevenLabsError, ElevenLabsTTS,
                             chunks, concat_mp3, french_voices, tts)


def slug(name: str) -> str:
    ascii_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', ascii_name.lower()).strip('-')[:40] or 'voix'


def render(text: str, voice_id: str, dest: Path, model: str, tempo: float = 1.0) -> None:
    parts: list[Path] = []
    for i, piece in enumerate(chunks(text)):
        part = dest.with_name(f'.{dest.stem}-{i:02d}.mp3')
        tts(piece, voice_id, part, model=model)
        parts.append(part)
    concat_mp3(parts, dest, tempo)
    for part in parts:
        part.unlink(missing_ok=True)


def run(params: dict, text: str, out: Path, lexicon: dict[str, str]) -> list[dict]:
    genre = 'homme' if str(params.get('genre', 'femme')).lower().startswith('h') else 'femme'
    model = params.get('modele') or DEFAULT_MODEL
    ids = [v for v in (params.get('voix_ids') or []) if v]
    voices = ([{'voice_id': v, 'name': v, 'source': 'choisie', 'accent': '', 'preview_url': ''}
               for v in ids] if ids else french_voices(genre, int(params.get('nombre', 4))))
    out.mkdir(parents=True, exist_ok=True)
    with_lexicon = params.get('lexique', True) is not False
    spoken = apply_lexicon(text, lexicon) if with_lexicon else text
    speeds = [float(x) for x in (params.get('vitesses') or [1.0])]
    results: list[dict] = []
    for n, v in enumerate(voices, 1):
        row = dict(v)
        name = f"{n:02d}-{slug(v['name'])}"
        files: list[str] = []
        try:
            for speed in speeds:
                suffix = '' if len(speeds) == 1 else f"-vitesse-{speed:g}".replace('.', '_')
                render(spoken, v['voice_id'], out / f'{name}{suffix}.mp3', model, speed)
                files.append(f'{name}{suffix}.mp3')
            row['fichier'] = ' · '.join(files)
            if n == 1 and with_lexicon:
                render(text, v['voice_id'], out / f'{name}-sans-lexique.mp3', model, speeds[0])
                row['fichier_sans_lexique'] = f'{name}-sans-lexique.mp3'
        except ElevenLabsError as exc:
            row['erreur'] = str(exc)
        results.append(row)
    lines = [f'# Casting voix {genre} — modèle {model} — lexique {"oui" if with_lexicon else "non"} — vitesses {speeds}', '',
             '| # | Voix | Source | Accent / langue | Fichier | voice_id |', '|---|---|---|---|---|---|']
    for n, r in enumerate(results, 1):
        f = r.get('fichier') or f"❌ {r.get('erreur', '')[:120]}"
        if r.get('fichier_sans_lexique'):
            f += f" · {r['fichier_sans_lexique']}"
        lines.append(f"| {n} | {r['name']} | {r['source']} | {r.get('accent', '')} | {f} | `{r['voice_id']}` |")
    if not results:
        lines.append('Aucune voix française (France) trouvée — ajouter des voix dans « Mes voix ».')
    (out / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (out / 'casting.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return results


def run_variants(params: dict, text: str, out: Path) -> list[dict]:
    """Même texte, même voix, plusieurs réglages : passe par le vrai moteur du
    podcast (ElevenLabsTTS), pour juger exactement ce qui sera diffusé.
    params['variantes'] = [{"nom": "...", "modele": "...", "vitesse": 1.15,
                            "reglages": {"stabilite": 1.0, "vitesse_native": 1.1}}]"""
    out.mkdir(parents=True, exist_ok=True)
    script = out / '.texte.txt'
    script.write_text(text, encoding='utf-8')
    voice = (params.get('voix_ids') or [DEFAULT_VOICE_FEMME])[0]
    results: list[dict] = []
    for n, v in enumerate(params['variantes'], 1):
        cfg = {'format': 'solo', 'voix_femme_elevenlabs': voice,
               'modele_elevenlabs': v.get('modele') or DEFAULT_MODEL,
               'vitesse': v.get('vitesse', 1.0), **{k: str(x) for k, x in (v.get('reglages') or {}).items()}}
        name = f"{n:02d}-{slug(v.get('nom') or cfg['modele_elevenlabs'])}.mp3"
        row = {'variante': v.get('nom', ''), **cfg}
        try:
            ElevenLabsTTS(cfg).synthesize(script, out / name)
            row['fichier'] = name
        except (ElevenLabsError, RuntimeError) as exc:
            row['erreur'] = str(exc)
        results.append(row)
    script.unlink(missing_ok=True)
    lines = ['# Casting réglages — voix ' + voice, '', '| # | Variante | Modèle | Réglages | Fichier |', '|---|---|---|---|---|']
    for n, r in enumerate(results, 1):
        reg = ', '.join(f'{k}={r[k]}' for k in ('vitesse', 'stabilite', 'similarite', 'style', 'vitesse_native', 'seed') if k in r)
        lines.append(f"| {n} | {r['variante']} | {r['modele_elevenlabs']} | {reg} | {r.get('fichier') or '❌ ' + r.get('erreur', '')[:150]} |")
    (out / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (out / 'casting.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description='Casting de voix ElevenLabs (rien n’est publié)')
    ap.add_argument('--params', type=Path, default=Path('.state/casting'))
    ap.add_argument('--texte', type=Path, default=Path('audio/texte-casting.txt'))
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    try:
        params = json.loads(args.params.read_text(encoding='utf-8')) if args.params.exists() else {}
    except ValueError:
        params = {}
    texte = Path(params['texte']) if params.get('texte') else args.texte
    if params.get('texte_ecoute'):  # un vrai transcript du podcast, lu sur la branche ecoute
        import subprocess
        subprocess.run(['git', 'fetch', '-q', '--depth', '1', 'origin', 'ecoute'], check=True, timeout=120)
        texte = Path('.texte-ecoute.txt')
        texte.write_text(subprocess.run(['git', 'show', f"FETCH_HEAD:{params['texte_ecoute']}"],
                                        check=True, capture_output=True, text=True).stdout, encoding='utf-8')
    try:
        if params.get('habillage'):
            from .audio import audio_config
            from .habillage import run as run_habillage
            results = run_habillage(params, args.out, audio_config())
            results = [{**r, 'fichier': r.get('demo')} for r in results]
        elif params.get('variantes'):
            results = run_variants(params, texte.read_text(encoding='utf-8'), args.out)
        else:
            results = run(params, texte.read_text(encoding='utf-8'), args.out, load_lexicon())
    except Exception as exc:  # noqa: BLE001 — on veut un README même en cas d'échec global
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'README.md').write_text(f'# Casting en échec\n\n{type(exc).__name__}: {exc}\n',
                                           encoding='utf-8')
        print(f'Casting en échec : {exc}', file=sys.stderr)
        return 1
    print(f'{sum(1 for r in results if r.get("fichier"))}/{len(results)} voix générées.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
