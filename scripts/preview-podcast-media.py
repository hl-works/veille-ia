#!/usr/bin/env python3
"""Prepare an existing edition without TTS; optionally send it once to Hugo privately."""
import argparse
from datetime import date
import json
import os
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from veille.audio import duration_seconds
from veille.podcast_media import TRACKS, prepare_media, validate_prepared
from veille.telegram import send_audio

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--day', required=True)
parser.add_argument('--output', type=Path, default=Path('audio-output'))
parser.add_argument('--send-private', action='store_true')
args = parser.parse_args()
day = date.fromisoformat(args.day).isoformat()
output = args.output
if not args.send_private:
    design = Path(os.environ['PODCAST_DESIGN_ROOT'])
    output.mkdir(parents=True, exist_ok=True)
    metadata = dict(date=day, destination='prive', telegram_sent=False, court_telegram_sent=False)
    for kind, (filename, key) in TRACKS.items():
        shutil.copyfile(design / f'assets/podcast/archive/{day}/{kind}.mp3', output / filename)
        metadata[key] = duration_seconds(output / filename)
    prepare_media(output, metadata)
    (output / 'brief.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print('Private preview prepared; no TTS, send or publication.')
else:
    if os.environ.get('GITHUB_EVENT_NAME') != 'workflow_dispatch' or os.environ.get('GITHUB_RUN_ATTEMPT') != '1':
        raise RuntimeError('Private send is manual and first attempt only')
    metadata = json.loads((output / 'brief.json').read_text())
    if metadata['destination'] != 'prive' or metadata['date'] != day:
        raise ValueError('Wrong preview destination or date')
    validate_prepared(output, metadata)
    token = os.environ['TELEGRAM_BOT_TOKEN']
    chat = os.environ['TELEGRAM_AUTHORIZED_USER_ID']
    if not token or not chat:
        raise RuntimeError('Private Telegram destination is not configured')
    for kind, (filename, key) in TRACKS.items():
        intent = output / f'{kind}-send-attempted'
        with intent.open('x') as marker:
            marker.write('Private preview upload attempted; do not replay automatically.\n')
        title = 'Le Flash' if kind == 'short' else 'Le Débrief'
        receipt = send_audio(output / filename, thumbnail=output / f'{kind}-thumbnail.jpg',
                   day=day, duration=metadata[key], bot_token=token, chat_id=chat,
                   title_prefix=title + ' · Le Podcast IA',
                   caption_suffix='aperçu privé de la pochette intégrée')
        (output / f'{kind}-telegram-receipt.json').write_text(json.dumps(receipt) + '\n')
        print(kind + ': private Telegram upload confirmed; ' + json.dumps(receipt))
