"""One cover before delivery; lossless MP3 tagging and bounded Telegram thumbnail."""
from datetime import date
import hashlib
import json
import logging
import math
import shutil
import os
from pathlib import Path
import subprocess
import sys
import tempfile

TRACKS = {'short': ('court.mp3', 'court_duration_seconds'),
          'full': ('brief.mp3', 'duration_seconds')}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(*args):
    return subprocess.check_output(args, timeout=180, stderr=subprocess.PIPE)


def image_info(path, size):
    streams = json.loads(command('ffprobe', '-v', 'error', '-show_entries',
                                'stream=codec_name,width,height', '-of', 'json', str(path)))['streams']
    if streams != [{'codec_name': 'mjpeg', 'width': size, 'height': size}]:
        raise ValueError('Invalid podcast JPEG')


def validate_thumbnail(path):
    path = Path(path)
    if not 0 < path.stat().st_size < 200_000:
        raise ValueError('Telegram thumbnail must be smaller than 200 kB')
    image_info(path, 320)


def audio_hash(path):
    return command('ffmpeg', '-nostdin', '-v', 'error', '-i', str(path),
                   '-map', '0:a:0', '-c:a', 'copy', '-f', 'hash', '-hash', 'sha256', '-')


def validate_prepared(output, metadata):
    """Validate both audio/image associations before sending or exporting either."""
    day = date.fromisoformat(metadata['date']).isoformat()
    artwork = metadata['artwork']
    if artwork['date'] != day:
        raise ValueError('Artwork date does not match audio')
    for kind, (filename, duration_key) in TRACKS.items():
        if kind == 'short' and metadata['court_duration_seconds'] == 0:
            continue
        track = artwork[kind]
        if track['seconds'] != metadata[duration_key]:
            raise ValueError('Artwork duration does not match audio')
        if track['image'] != f'/assets/podcast/archive/{day}/{kind}-cover-v2.jpg':
            raise ValueError('Unexpected artwork path')
        for path, checksum in [(output / filename, track['audio_sha256']),
                               (output / f'{kind}-cover.jpg', track['image_sha256']),
                               (output / f'{kind}-cover.png', track['png_sha256']),
                               (output / f'{kind}-thumbnail.jpg', track['thumbnail_sha256'])]:
            if sha(path) != checksum:
                raise ValueError('Prepared media changed')
        image_info(output / f'{kind}-cover.jpg', 3000)
        validate_thumbnail(output / f'{kind}-thumbnail.jpg')
    return artwork


def prepare_media(output, metadata):
    """Render once, attach artwork without re-encoding, then seal the association."""
    design = os.environ.get('PODCAST_DESIGN_ROOT')
    if not design:
        raise RuntimeError('PODCAST_DESIGN_ROOT is required for artwork rendering')
    renderer = Path(design).resolve() / 'scripts/render_podcast_covers.py'
    output = Path(output).resolve()
    # Missing/invalid short or full duration fails before any Telegram request.
    command(sys.executable, str(renderer), '--daily', metadata['date'],
            '--short-seconds', str(metadata['court_duration_seconds']),
            '--full-seconds', str(metadata['duration_seconds']), '--output', str(output))
    artwork = json.loads((output / 'artwork.json').read_text())
    with tempfile.TemporaryDirectory(dir=output) as directory:
        stage = Path(directory)
        for kind, (filename, _) in TRACKS.items():
            if kind not in artwork:
                continue
            cover = output / f'{kind}-cover.jpg'
            image_info(cover, 3000)
            thumb = output / f'{kind}-thumbnail.jpg'
            command('ffmpeg', '-nostdin', '-y', '-v', 'error', '-i', str(cover),
                    '-vf', 'scale=320:320', '-frames:v', '1', '-q:v', '3', str(thumb))
            validate_thumbnail(thumb)
            embedded = stage / f'{kind}-embedded.jpg'
            command('ffmpeg', '-nostdin', '-y', '-v', 'error', '-i', str(cover),
                    '-vf', 'scale=1080:1080', '-frames:v', '1', '-q:v', '3', str(embedded))
            source, tagged = output / filename, stage / filename
            title = ('Le Flash' if kind == 'short' else 'Le Débrief') + ' — ' + metadata['date']
            command('ffmpeg', '-nostdin', '-y', '-v', 'error', '-i', str(source),
                    '-i', str(embedded), '-map', '0:a:0', '-map', '1:v:0', '-c', 'copy',
                    '-id3v2_version', '3', '-disposition:v:0', 'attached_pic',
                    '-metadata', f'title={title}', '-metadata', 'artist=Hugo LaHutte',
                    '-metadata', 'album=Le Podcast IA', '-metadata:s:v', 'title=Cover',
                    '-metadata:s:v', 'comment=Cover (front)', str(tagged))
            if not 1024 < tagged.stat().st_size < 25_000_000:
                raise ValueError('Illustrated MP3 exceeds the shared publication limits')
            if audio_hash(source) != audio_hash(tagged):
                raise ValueError('Audio stream changed while attaching artwork')
            probe = json.loads(command('ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(tagged)))
            pictures = [s for s in probe['streams'] if s.get('disposition', {}).get('attached_pic') == 1]
            if len(pictures) != 1 or pictures[0]['width'] != 1080:
                raise ValueError('Embedded cover missing')
            artwork[kind].update(audio_sha256=sha(tagged), png_sha256=sha(output / f'{kind}-cover.png'),
                                 thumbnail_sha256=sha(thumb))
        # Neither track is sent until both have passed all checks.
        for kind, (filename, _) in TRACKS.items():
            if kind in artwork:
                (stage / filename).replace(output / filename)
    metadata['artwork'] = artwork
    validate_prepared(output, metadata)
    return artwork


def validate_audio(path, seconds):
    """Audio integrity remains mandatory even when artwork is unavailable."""
    path = Path(path)
    if not path.is_file() or not 1024 < path.stat().st_size < 25_000_000:
        raise ValueError('Missing or invalid MP3')
    probe = json.loads(command('ffprobe', '-v', 'error', '-show_entries',
                              'format=duration:stream=codec_name,codec_type', '-of', 'json', str(path)))
    actual = float(probe['format']['duration'])
    streams = [s for s in probe['streams'] if s.get('codec_type') == 'audio']
    if (len(streams) != 1 or streams[0]['codec_name'] != 'mp3' or not math.isfinite(actual)
            or type(seconds) is not int or not 0 < seconds < 1800 or abs(actual - seconds) > 2):
        raise ValueError('Invalid MP3 codec or duration')
    return sha(path)


def prepare_with_fallback(output, metadata):
    """Artwork is best effort. Restore the verified originals on ANY cover failure."""
    output = Path(output)
    tracks = {kind: values for kind, values in TRACKS.items()
              if kind == 'full' or metadata['court_duration_seconds'] > 0}
    originals = {kind: validate_audio(output / filename, metadata[key])
                 for kind, (filename, key) in tracks.items()}
    with tempfile.TemporaryDirectory(dir=output) as directory:
        backup = Path(directory)
        for filename, _ in tracks.values():
            shutil.copyfile(output / filename, backup / filename)
        try:
            prepare_media(output, metadata)
            metadata['audio_sha256'] = {kind: validate_audio(output / filename, metadata[key])
                                        for kind, (filename, key) in tracks.items()}
            metadata['artwork_status'] = 'ready'
        except Exception as exc:
            # Rendering/remuxing may have replaced one file before failing.
            # Restore BOTH originals; never send a partially tagged/corrupt pair.
            for filename, _ in tracks.values():
                shutil.copyfile(backup / filename, output / filename)
            metadata.pop('artwork', None)
            metadata['artwork_status'] = 'unavailable'
            metadata['audio_sha256'] = originals
            metadata['artwork_error'] = type(exc).__name__
            logging.getLogger(__name__).warning(
                'Pochette indisponible (%s) : publication des audios vérifiés sans image.',
                type(exc).__name__)
        for kind, (filename, key) in tracks.items():
            if validate_audio(output / filename, metadata[key]) != metadata['audio_sha256'][kind]:
                raise ValueError('Audio changed during preparation')
    return metadata.get('artwork')
