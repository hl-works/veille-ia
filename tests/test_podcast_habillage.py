"""Podcast quotidien : habillage (jingles entre les sujets) et version courte."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from veille import audio, telegram
from veille.config import Settings

MESSAGE = '<b>Agents IA</b>\nUn outil facilite les tests.\n<a href="https://example.org/source">Source</a>'


class HabillageTests(unittest.TestCase):
    def test_sections_split_on_transition_markers(self):
        script = 'Bonjour.\n\nSujet A.\n---\nSujet B.\n\nSuite B.\n  ---  \nFin.'
        self.assertEqual(audio.split_sections(script), ['Bonjour.\n\nSujet A.', 'Sujet B.\n\nSuite B.', 'Fin.'])
        self.assertNotIn('---', audio.clean_script(script))
        self.assertIn('FORMAT SOLO', audio.SCRIPT_PROMPT)
        self.assertIn('---', audio.SCRIPT_PROMPT)
        self.assertIn("L'ESSENTIEL", audio.COURT_PROMPT)
        self.assertIn("N'ajoute aucun sujet", audio.COURT_PROMPT)

    def test_render_with_jingles_synthesizes_each_section(self):
        provider = Mock()
        provider.synthesize.side_effect = lambda script, out: out.write_bytes(script.read_bytes())
        with tempfile.TemporaryDirectory() as directory, \
             patch('veille.habillage.assemble') as assemble:
            out = Path(directory) / 'o.mp3'
            audio.render('A.\n---\nB.\n---\nC.', provider, out, {'intro': 'i'})
            self.assertEqual(provider.synthesize.call_count, 3)
            voices, pieces, dest = assemble.call_args.args
            self.assertEqual(len(voices), 3)
            self.assertEqual(dest, out)

    def test_render_without_jingles_is_one_synthesis_without_markers(self):
        seen = []
        provider = Mock()
        provider.synthesize.side_effect = lambda script, out: (seen.append(script.read_text()), out.write_bytes(b'x'))
        with tempfile.TemporaryDirectory() as directory:
            audio.render('A.\n---\nB.', provider, Path(directory) / 'o.mp3', None)
        self.assertEqual(seen, ['A.\n\nB.'])

    def test_short_version_sent_first_and_never_blocks_long(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.json'
            audio.save_snapshot(MESSAGE, '10/09/2026', str(source))
            provider = Mock()
            provider.synthesize.side_effect = lambda script, out: out.write_bytes(b'mp3')
            cfg = {**audio.DEFAULT_AUDIO, 'version_courte': 'true'}
            settings = Settings(telegram_bot_token='t')
            scripts = lambda snap, st, fmt='solo', version='longue': 'Court.' if version == 'courte' else 'Long.'
            with patch.dict('os.environ', {'TELEGRAM_AUTHORIZED_USER_ID': '42'}), \
                 patch.object(audio, 'build_script', side_effect=scripts), \
                 patch.object(audio, 'get_provider', return_value=provider), \
                 patch.object(audio, 'duration_seconds', side_effect=lambda p: 90 if p.name == 'court.mp3' else 390), \
                 patch.object(telegram, 'send_audio') as send:
                audio.run(source, root / 'out', settings, send=True, cfg=cfg)
            self.assertEqual([c.args[0].name for c in send.call_args_list], ['court.mp3', 'brief.mp3'])
            self.assertIn('6 min 30', send.call_args_list[0].kwargs['caption_suffix'])
            meta = json.loads((root / 'out/brief.json').read_text())
            self.assertEqual((meta['court_duration_seconds'], meta['telegram_sent']), (90, True))
            self.assertEqual((root / 'out/transcript-court.txt').read_text(), 'Court.')
            # Échec de la version courte : la longue part quand même.
            failing = lambda snap, st, fmt='solo', version='longue': (_ for _ in ()).throw(RuntimeError('x')) if version == 'courte' else 'Long.'
            with patch.dict('os.environ', {'TELEGRAM_AUTHORIZED_USER_ID': '42'}), \
                 patch.object(audio, 'build_script', side_effect=failing), \
                 patch.object(audio, 'get_provider', return_value=provider), \
                 patch.object(audio, 'duration_seconds', return_value=390), \
                 patch.object(telegram, 'send_audio') as send:
                audio.run(source, root / 'out2', settings, send=True, cfg=cfg)
            self.assertEqual([c.args[0].name for c in send.call_args_list], ['brief.mp3'])

    def test_missing_jingles_fall_back_to_plain_podcast(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('veille.habillage.fetch_pieces', side_effect=RuntimeError('git')):
            self.assertIsNone(audio._pieces({'habillage': 'ecoute:x/y'}, Path(directory)))
            self.assertIsNone(audio._pieces({'habillage': ''}, Path(directory)))

    def test_assemble_leaves_no_gap_between_music_and_voice(self):
        import shutil, subprocess
        if not shutil.which('ffmpeg'):
            self.skipTest('ffmpeg absent')
        from veille import habillage
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            def tone(name, secs, tail=0.0):
                f = d / name
                subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                                f'sine=frequency=440:duration={secs}', '-af', f'apad=pad_dur={tail}', str(f)], check=True)
                return f
            pieces = {'intro': tone('i.mp3', 2, tail=3), 'transition': tone('t.mp3', 1, tail=2),
                      'outro': tone('o.mp3', 2, tail=2)}
            out = d / 'out.mp3'
            habillage.assemble([tone('v1.mp3', 2), tone('v2.mp3', 2)], pieces, out)
            log = subprocess.run(['ffmpeg', '-nostdin', '-i', str(out), '-af', 'silencedetect=noise=-40dB:d=0.5',
                                  '-f', 'null', '-'], capture_output=True, text=True).stderr
            self.assertNotIn('silence_start', log)
            duration = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                             '-of', 'csv=p=0', str(out)], capture_output=True, text=True).stdout)
            self.assertLess(duration, 9.5)  # 2+2+1+2+2 = 9 s de son, blancs de 7 s supprimés


if __name__ == '__main__':
    unittest.main()
