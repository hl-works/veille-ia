"""Voix ElevenLabs (modèle eleven_v3 par défaut) pour le podcast Veille IA.

Clé : variable d'environnement ELEVENLABS_API_KEY (secret GitHub).
Règle d'Hugo : accent de France uniquement — jamais de voix canadienne,
belge, suisse ou africaine (filtre ACCENTS_EXCLUS).
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

import requests

API = 'https://api.elevenlabs.io'
DEFAULT_MODEL = 'eleven_v3'
CHUNK_LIMIT = 2500  # marge sous la limite par requête du modèle
# Voix validée par Hugo le 25/09/2026 (casting) : Victoria, français de France.
DEFAULT_VOICE_FEMME = 'uOw88F5bjqRiVuZLhXEA'

ACCENTS_EXCLUS = re.compile(
    r'canad|qu[eé]b|belg|swiss|suisse|afric|cameroun|s[eé]n[eé]gal|ivoir|congo|'
    r'morocc|maroc|alg[eé]r|tunis|ha[iï]ti|antill|caribb|martiniq|guadeloup|r[eé]union',
    re.I)


class ElevenLabsError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f'ElevenLabs HTTP {status} : {detail[:300]}')
        self.status = status


def _key() -> str:
    key = os.environ.get('ELEVENLABS_API_KEY', '')
    if not key:
        raise RuntimeError('ELEVENLABS_API_KEY absent')
    return key


def _get(path: str, params: dict | None = None) -> dict:
    r = requests.get(f'{API}{path}', params=params or {},
                     headers={'xi-api-key': _key()}, timeout=(10, 60))
    if not r.ok:
        raise ElevenLabsError(r.status_code, r.text)
    return r.json()


def tts(text: str, voice_id: str, dest: Path, *, model: str = DEFAULT_MODEL) -> None:
    """Une requête de synthèse → un MP3. Réessaie sans language_code si le
    modèle le refuse."""
    body = {'text': text, 'model_id': model, 'language_code': 'fr'}
    for attempt in range(2):
        r = requests.post(f'{API}/v1/text-to-speech/{voice_id}',
                          params={'output_format': 'mp3_44100_128'},
                          headers={'xi-api-key': _key(), 'accept': 'audio/mpeg'},
                          json=body, timeout=(10, 300))
        if r.ok and r.content:
            dest.write_bytes(r.content)
            return
        if attempt == 0 and r.status_code in (400, 422) and 'language' in r.text.lower():
            body.pop('language_code', None)
            continue
        raise ElevenLabsError(r.status_code, r.text)


def chunks(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    """Découpe par paragraphes puis par phrases, sans perdre un mot."""
    out: list[str] = []
    cur = ''
    for para in re.split(r'\n\s*\n', text.strip()):
        pieces = [para] if len(para) <= limit else re.split(r'(?<=[.!?…])\s+', para)
        for piece in pieces:
            while len(piece) > limit:  # phrase géante : coupe sur un espace
                cut = piece.rfind(' ', 0, limit)
                cut = cut if cut > 0 else limit
                out.append(piece[:cut].strip())
                piece = piece[cut:].strip()
            cand = f'{cur}\n\n{piece}' if cur else piece
            if len(cand) <= limit:
                cur = cand
            else:
                out.append(cur)
                cur = piece
    if cur:
        out.append(cur)
    return [c for c in out if c.strip()]


def concat_mp3(files: list[Path], output: Path, tempo: float = 1.0) -> None:
    """Assemble les morceaux en un MP3. `tempo` > 1 accélère le débit sans
    changer la hauteur de la voix (filtre atempo, 0.5 à 2.0)."""
    listing = output.parent / f'.{output.stem}-list.txt'
    listing.write_text(''.join(f"file '{f.resolve()}'\n" for f in files), encoding='utf-8')
    tempo = min(2.0, max(0.5, float(tempo or 1.0)))
    filters = ['-filter:a', f'atempo={tempo:g}'] if abs(tempo - 1.0) > 1e-3 else []
    try:
        subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-f', 'concat', '-safe', '0',
                        '-i', str(listing), *filters, '-ac', '1', '-ar', '44100', '-codec:a', 'libmp3lame',
                        '-b:a', '96k', str(output)], check=True, timeout=300,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        listing.unlink(missing_ok=True)


class ElevenLabsTTS:
    """Fournisseur TTS pour veille.audio (même interface que EdgeTTS)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model = cfg.get('modele_elevenlabs') or DEFAULT_MODEL

    def _voice(self, who: str) -> str:
        key = 'voix_homme_elevenlabs' if who == 'homme' else 'voix_femme_elevenlabs'
        voice = self.cfg.get(key, '') or (DEFAULT_VOICE_FEMME if who != 'homme' else '')
        if not voice:
            raise RuntimeError(f'Aucune voix ElevenLabs choisie ({key} vide) — lancer le casting')
        return voice

    def synthesize(self, script_path: Path, output: Path) -> None:
        from .audio import segments
        parts = segments(script_path.read_text(encoding='utf-8'), self.cfg.get('format', 'solo'))
        if not parts:
            raise RuntimeError('Script sans contenu parlé')
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as directory:
            files: list[Path] = []
            for who, text in parts:
                for piece in chunks(text):
                    dest = Path(directory) / f'{len(files):04d}.mp3'
                    tts(piece, self._voice(who), dest, model=self.model)
                    files.append(dest)
            concat_mp3(files, output, float(self.cfg.get('vitesse', 1.0) or 1.0))


# ── Découverte des voix françaises (pour le casting) ────────────────────────

def _desc(v: dict) -> str:
    labels = v.get('labels') or {}
    langs = v.get('verified_languages') or []
    bits = [str(v.get('accent') or ''), str(v.get('locale') or ''), str(v.get('language') or ''),
            ' '.join(f"{k}:{x}" for k, x in labels.items()),
            ' '.join(f"{l.get('language')}/{l.get('accent')}/{l.get('locale')}" for l in langs)]
    return ' '.join(b for b in bits if b)


ACCENTS_ANGLO = re.compile(r'americ|british|english|austral|irish|scott|us\b|uk\b|en-US|en-GB', re.I)


def is_france_french(v: dict) -> bool:
    """Voix dont la langue PRINCIPALE est le français de France. Les voix
    anglophones « multilingues » (qui parlent aussi français, avec accent)
    sont exclues, tout comme les accents canadien, belge, suisse, africain."""
    labels = v.get('labels') or {}
    language = str(labels.get('language') or v.get('language') or '').lower()
    accent = str(labels.get('accent') or v.get('accent') or '')
    locale = str(v.get('locale') or '')
    if not (language.startswith('fr') or 'french' in language or 'fran' in language):
        return False
    if ACCENTS_EXCLUS.search(f'{accent} {locale}') or ACCENTS_ANGLO.search(accent):
        return False
    if locale and not locale.lower().startswith('fr-fr') and locale.lower() != 'fr':
        return False
    return True


def french_voices(gender: str, limit: int) -> list[dict]:
    """Voix du compte d'abord (celles qu'Hugo a ajoutées), puis la bibliothèque
    partagée. Chaque entrée : voice_id, name, accent, source, preview_url."""
    found: list[dict] = []
    seen: set[str] = set()
    gender_en = 'male' if gender == 'homme' else 'female'

    def add(v: dict, source: str) -> None:
        vid = v.get('voice_id')
        if not vid or vid in seen:
            return
        g = str((v.get('labels') or {}).get('gender') or v.get('gender') or '').lower()
        if g and g != gender_en:
            return
        if not is_france_french(v):
            return
        seen.add(vid)
        found.append({'voice_id': vid, 'name': v.get('name', '?'), 'source': source,
                      'public_owner_id': v.get('public_owner_id', ''),
                      'accent': _desc(v)[:120], 'preview_url': v.get('preview_url', '')})

    try:
        for v in _get('/v2/voices', {'page_size': 100}).get('voices', []):
            add(v, 'mes voix')
    except ElevenLabsError:
        pass
    if len(found) < limit:
        data = _get('/v1/shared-voices', {'language': 'fr', 'gender': gender_en,
                                          'page_size': 100})
        for v in data.get('voices', []):
            add(v, 'bibliothèque')
    return found[:limit]
