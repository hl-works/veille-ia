#!/usr/bin/env python3
"""Export only a complete pair already published to the public Telegram channel."""
import argparse
from datetime import date
import hashlib
import json
import math
import logging
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from veille.podcast_media import validate_prepared


def export_full_only(source: Path, destination: Path, data: dict) -> bool:
    """Jour sans Flash : le Débrief part quand même sur les plateformes (RSS/Spotify).

    Ajouté à platform-episodes.json, sans toucher au duo du site (latest.json).
    """
    day = date.fromisoformat(data['date']).isoformat()
    platform = destination / 'platform-episodes.json'
    manifest = json.loads(platform.read_text()) if platform.exists() else {'episodes': []}
    known = {e['date'] for e in manifest['episodes']}
    site = destination / 'episodes.json'
    if site.exists():
        known |= {e['date'] for e in json.loads(site.read_text())['episodes']}
    if day in known:
        return False
    audio = source / 'brief.mp3'
    seconds = data['duration_seconds']
    actual = float(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=nw=1:nk=1', str(audio)], text=True, timeout=30))
    if not 1024 < audio.stat().st_size < 25_000_000 or not math.isfinite(actual) \
            or not isinstance(seconds, int) or not 0 < seconds < 1800 or abs(actual - seconds) > 2:
        raise ValueError('Invalid audio duration')
    folder = destination / 'archive' / day
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(audio, folder / 'full.mp3')
    track = {'src': f'/assets/podcast/archive/{day}/full.mp3', 'seconds': seconds,
             'bytes': audio.stat().st_size, 'sha256': hashlib.sha256(audio.read_bytes()).hexdigest()}
    cover = source / 'full-cover.jpg'
    if data.get('artwork') and cover.is_file():
        try:
            validate_prepared(source, data)
            shutil.copyfile(cover, folder / 'full-cover-v2.jpg')
            track.update(image=f'/assets/podcast/archive/{day}/full-cover-v2.jpg',
                         image_sha256=hashlib.sha256(cover.read_bytes()).hexdigest())
        except Exception as exc:
            logging.warning('Pochette indisponible à l’export (%s).', type(exc).__name__)
    manifest['episodes'].append({'date': day, 'full': track})
    manifest['episodes'].sort(key=lambda e: e['date'], reverse=True)
    platform.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return True


def export(source: Path, destination: Path) -> bool:
    metadata = source / 'brief.json'
    if not metadata.exists():
        return False
    data = json.loads(metadata.read_text())
    if (data.get('destination') == 'canal' and data.get('telegram_sent') is True
            and data.get('court_duration_seconds') == 0):
        return export_full_only(source, destination, data)
    if (data.get('destination') != 'canal' or data.get('telegram_sent') is not True
            or data.get('court_telegram_sent') is not True):
        return False
    day = date.fromisoformat(data['date']).isoformat()
    previous = destination / 'latest.json'
    if previous.exists() and json.loads(previous.read_text())['date'] > day:
        return False  # A retry of an old run must not replace a newer episode.
    manifest = {'date': day}
    digest = hashlib.sha256()
    files = [('short', 'court.mp3', 'court_duration_seconds'),
             ('full', 'brief.mp3', 'duration_seconds')]
    for name, filename, key in files:
        path = source / filename
        if not path.is_file() or not 1024 < path.stat().st_size < 25_000_000:
            raise ValueError('Missing or invalid audio file')
        actual = float(subprocess.check_output([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=nw=1:nk=1', str(path)], text=True, timeout=30))
        seconds = data[key]
        if not math.isfinite(actual) or not isinstance(seconds, int) or not 0 < seconds < 1800 or abs(actual - seconds) > 2:
            raise ValueError('Invalid audio duration')
        expected_hash = data.get('audio_sha256', {}).get(name) or data.get('artwork', {}).get(name, {}).get('audio_sha256')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise ValueError('Prepared audio changed')
        digest.update(path.read_bytes())
        manifest[name] = {'src': f'/assets/podcast/{name}.mp3', 'seconds': seconds}
    manifest['version'] = digest.hexdigest()[:16]
    artwork = None
    if data.get('artwork'):
        try:
            artwork = validate_prepared(source, data)
            for name, _, _ in files:
                target = destination / 'archive' / day / f'{name}-cover-v2.jpg'
                if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != artwork[name]['image_sha256']:
                    raise ValueError('Published artwork is immutable')
        except Exception as exc:
            logging.warning('Pochette indisponible à l’export (%s) : RSS sans image d’épisode.', type(exc).__name__)
            artwork = None
    for name, _, _ in files:
        if artwork:
            manifest[name].update(image=artwork[name]['image'], image_sha256=artwork[name]['image_sha256'])
    manifest['artwork_status'] = 'ready' if artwork else 'unavailable'
    # Validate BOTH tracks before touching the current publication.
    destination.mkdir(parents=True, exist_ok=True)
    for name, filename, _ in files:
        shutil.copyfile(source / filename, destination / f'{name}.mp3')
        if not artwork:
            continue
        target = destination / 'archive' / day / f'{name}-cover-v2.jpg'
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(source / f'{name}-cover.jpg', target)
        png = destination / 'covers' / f'{day}-{name}.png'
        png.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / f'{name}-cover.png', png)
    previous.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print('Podcast exporté.' if export(args.source, args.destination) else 'Aucun duo public plus récent à publier.')
