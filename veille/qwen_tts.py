"""Qwen worker: optional environment, chunked French synthesis, mono MP3."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile


def chunks(text: str, limit: int = 450) -> list[str]:
    """Bound inference context without discarding any word of the script."""
    result, current = [], ''
    for sentence in re.split(r'(?<=[.!?])\s+|\n+', text.strip()):
        for word in sentence.split():
            if current and len(current) + len(word) + 1 > limit:
                result.append(current)
                current = ''
            current = f'{current} {word}'.strip()
        if current:
            result.append(current)
            current = ''
    return result


def synthesize(script: str, output: Path) -> None:
    import torch
    import soundfile as sf
    from qwen_tts import Qwen3TTSModel

    device = os.environ.get('QWEN_DEVICE', 'cpu')
    model = Qwen3TTSModel.from_pretrained(
        os.environ.get('QWEN_MODEL', 'Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice'),
        device_map=device,
        dtype=torch.float32 if device == 'cpu' else torch.bfloat16,
        attn_implementation='sdpa')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        wav = Path(directory) / 'brief.wav'
        writer = None
        try:
            for part in chunks(script):
                waves, rate = model.generate_custom_voice(
                    text=part, language='French', speaker=os.environ.get('QWEN_SPEAKER', 'Ryan'),
                    non_streaming_mode=True, max_new_tokens=4096)
                if writer is None:
                    writer = sf.SoundFile(wav, mode='w', samplerate=rate, channels=1, subtype='PCM_16')
                if rate != writer.samplerate:
                    raise ValueError('Fréquence audio variable')
                writer.write(waves[0])
        finally:
            if writer is not None:
                writer.close()
        subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-i', str(wav),
                        '-ac', '1', '-ar', '24000', '-codec:a', 'libmp3lame',
                        '-b:a', '64k', str(output)], check=True, timeout=120,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--script', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    synthesize(args.script.read_text(encoding='utf-8'), args.output)
