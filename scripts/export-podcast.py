#!/usr/bin/env python3
"""Export only a complete pair already published to the public Telegram channel."""
import argparse
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from veille.podcast_media import validate_prepared


def export(source: Path, destination: Path) -> bool:
    metadata = source / 'brief.json'
    if not metadata.exists():
        return False
    data = json.loads(metadata.read_text())
    if (data.get('destination') != 'canal' or data.get('telegram_sent') is not True
            or data.get('court_telegram_sent') is not True):
        return False
    day = date.fromisoformat(data['date']).isoformat()
    previous = destination / 'latest.json'
    if previous.exists() and json.loads(previous.read_text())['date'] > day:
        return False  # A retry of an old run must not replace a newer episode.
    artwork = validate_prepared(source, data)
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
        digest.update(path.read_bytes())
        manifest[name] = {'src': f'/assets/podcast/{name}.mp3', 'seconds': seconds,
                          'image': artwork[name]['image'],
                          'image_sha256': artwork[name]['image_sha256']}
    manifest['version'] = digest.hexdigest()[:16]
    # Never change an already published dated image, including concurrent retries.
    for name, _, _ in files:
        target = destination / 'archive' / day / f'{name}-cover-v2.jpg'
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != artwork[name]['image_sha256']:
            raise ValueError('Published artwork is immutable')
    # Validate BOTH tracks before touching the current publication.
    destination.mkdir(parents=True, exist_ok=True)
    for name, filename, _ in files:
        shutil.copyfile(source / filename, destination / f'{name}.mp3')
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
