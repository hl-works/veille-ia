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


def tts(text: str, voice_id: str, dest: Path, *, model: str = DEFAULT_MODEL,
        previous_text: str = '', next_text: str = '', voice_settings: dict | None = None,
        seed: int | None = None) -> None:
    """Une requête de synthèse → un MP3.
    previous_text / next_text : le texte voisin, pour que l'intonation reste
    continue d'un morceau à l'autre (sinon : sauts de voix ou de débit).
    Un paramètre refusé par le modèle (400/422) est retiré et la requête rejouée."""
    body: dict = {'text': text, 'model_id': model, 'language_code': 'fr'}
    if previous_text:
        body['previous_text'] = previous_text[-1000:]
    if next_text:
        body['next_text'] = next_text[:1000]
    if voice_settings:
        body['voice_settings'] = voice_settings
    if seed is not None:
        body['seed'] = int(seed)
    optional = ['language_code', 'previous_text', 'next_text', 'seed', 'voice_settings']
    for _ in range(len(optional) + 1):
        r = requests.post(f'{API}/v1/text-to-speech/{voice_id}',
                          params={'output_format': 'mp3_44100_128'},
                          headers={'xi-api-key': _key(), 'accept': 'audio/mpeg'},
                          json=body, timeout=(10, 300))
        if r.ok and r.content:
            dest.write_bytes(r.content)
            return
        if r.status_code in (400, 422):
            low = r.text.lower()
            culprit = next((k for k in optional if k in body and k.split('_')[0] in low), None)
            if culprit:
                body.pop(culprit, None)
                continue
        raise ElevenLabsError(r.status_code, r.text)
    raise ElevenLabsError(400, 'paramètres refusés')


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
    changer la hauteur de la voix (filtre atempo, 0.5 à 2.0). Le volume est
    normalisé (loudnorm, -16 LUFS) pour éviter les écarts de niveau."""
    listing = output.parent / f'.{output.stem}-list.txt'
    listing.write_text(''.join(f"file '{f.resolve()}'\n" for f in files), encoding='utf-8')
    tempo = min(2.0, max(0.5, float(tempo or 1.0)))
    chain = ([f'atempo={tempo:g}'] if abs(tempo - 1.0) > 1e-3 else []) + ['loudnorm=I=-16:TP=-1.5:LRA=11']
    try:
        subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-f', 'concat', '-safe', '0',
                        '-i', str(listing), '-filter:a', ','.join(chain), '-ac', '1', '-ar', '44100',
                        '-codec:a', 'libmp3lame', '-b:a', '128k', str(output)], check=True, timeout=300,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        listing.unlink(missing_ok=True)


def voice_settings_from(cfg: dict) -> dict:
    """Réglages de voix lus dans audio.yaml (clés stabilite, similarite, style,
    vitesse_native). Vide = réglages par défaut de la voix."""
    mapping = {'stabilite': 'stability', 'similarite': 'similarity_boost',
               'style': 'style', 'vitesse_native': 'speed'}
    out = {}
    for fr, en in mapping.items():
        v = cfg.get(fr)
        if v not in (None, ''):
            out[en] = float(v)
    return out


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
        # Un même locuteur = un seul flux de texte (les paragraphes ne sont plus
        # envoyés un par un : c'était la cause des sauts de voix et de débit).
        merged: list[list[str]] = []
        for who, text in parts:
            if merged and merged[-1][0] == who:
                merged[-1][1] += '\n\n' + text
            else:
                merged.append([who, text])
        pieces = [(who, piece) for who, text in merged for piece in chunks(text)]
        settings = voice_settings_from(self.cfg)
        seed = int(self.cfg['seed']) if str(self.cfg.get('seed', '')).strip() else None
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as directory:
            files: list[Path] = []
            for i, (who, piece) in enumerate(pieces):
                dest = Path(directory) / f'{i:04d}.mp3'
                tts(piece, self._voice(who), dest, model=self.model,
                    previous_text=pieces[i - 1][1] if i else '',
                    next_text=pieces[i + 1][1] if i + 1 < len(pieces) else '',
                    voice_settings=settings, seed=seed)
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
