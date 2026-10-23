"""Casting contract: both formats, strict roles and isolated voice processing."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from veille import audio, elevenlabs_tts as el

SCRIPT = "IASTRO: Salut, c'est iAstro !\nVICTORIA: Le premier fait.\n---\nIASTRO: Et maintenant ?\nVICTORIA: La suite.\nVICTORIA: Son contexte.\nIASTRO: À très vite !"


class IAstroTests(unittest.TestCase):
    def test_prompts_and_strict_roles(self):
        for version, label in [('courte', 'Flash'), ('longue', 'Débrief')]:
            prompt = audio.script_prompt('iastro', version)
            self.assertIn(f'FORMAT : {label}', prompt)
            self.assertIn('N’annonce jamais'.replace('’', "'"), prompt)
            self.assertNotIn("sa voix n'est pas encore intégrée", prompt)
        audio.validate_iastro_script(SCRIPT)
        parts = audio.segments(audio.clean_script(SCRIPT), 'iastro')
        self.assertEqual([p[0] for p in parts], ['iastro', 'femme', 'iastro', 'femme', 'femme', 'iastro'])
        self.assertEqual(parts[0][1], "Salut, c'est iAstro !")
        for bad in ('Bonjour', 'VICTORIA: Bonjour', 'IASTRO: Salut\nBOB: Qui ?',
                    'IASTRO: Salut\nVICTORIA: ', SCRIPT.rsplit('\n', 1)[0]):
            with self.assertRaises(ValueError):
                audio.validate_iastro_script(bad)

    def test_production_config_and_no_silent_voice_fallback(self):
        cfg = audio.audio_config()
        self.assertEqual(cfg['format'], 'iastro')
        self.assertEqual(cfg['voix_iastro_elevenlabs'], 'Yx2a8qp2EqI9c5i8MzBo')
        for provider in ('edge', 'qwen'):
            with self.assertRaises(ValueError):
                audio.get_provider(dict(cfg, provider=provider))

    def test_iastro_tts_victoria_dialogue_and_only_host_accelerated(self):
        calls = []
        cfg = dict(audio.audio_config(), seed='42')
        def tts(text, voice, dest, **kw):
            calls.append(('tts', voice, text, kw))
            dest.write_bytes(b'x')
        def dialogue(lines, dest, **kw):
            calls.append(('dialogue', lines, kw))
            dest.write_bytes(b'x')
        with tempfile.TemporaryDirectory() as d, patch.object(el, 'tts', side_effect=tts), \
                patch.object(el, 'dialogue', side_effect=dialogue), patch.object(el, 'concat_mp3') as cat:
            path = Path(d) / 'script.txt'; path.write_text(audio.clean_script(SCRIPT.replace("iAstro !", "iAstro ! Bienvenue dans le Débrief.")))
            el.ElevenLabsTTS(cfg).synthesize(path, Path(d) / 'out.mp3')
            deessed = [c for c in cat.call_args_list if c.kwargs.get('deess')]
            self.assertEqual(len(deessed), 3)
            self.assertTrue(all(c.args[2] == 1.15 for c in deessed))
            for c in cat.call_args_list:
                if not c.kwargs.get('deess'):
                    self.assertEqual(c.args[2] if len(c.args) > 2 else 1.0, 1.0)
        self.assertEqual(calls[0][2], 'Bienvenue dans le Débrief.')
        self.assertTrue(all('iAstro' not in c[2] for c in calls if c[0] == 'tts'))
        self.assertEqual(cat.call_args.args[0][0], el.APPROVED_IASTRO_GREETING)
        self.assertEqual([c[0] for c in calls], ['tts', 'dialogue', 'tts', 'dialogue', 'tts'])
        for c in calls:
            if c[0] == 'tts':
                self.assertEqual(c[1], cfg['voix_iastro_elevenlabs'])
                self.assertEqual(c[3]['voice_settings'], {'stability': 0.5, 'similarity_boost': 0.75})
            else:
                self.assertTrue(all(voice == cfg['voix_femme_elevenlabs'] for voice, _ in c[1]))
                self.assertEqual(c[2]['model'], 'eleven_v4')
        self.assertIn('Son contexte.', ' '.join(text for _, text in calls[3][1]))

    def test_greeting_only_never_calls_voice_service(self):
        cfg = audio.audio_config()
        with tempfile.TemporaryDirectory() as d, patch.object(el, 'tts') as synth, \
                patch.object(el, 'concat_mp3') as cat:
            path = Path(d) / 'script.txt'
            path.write_text("IASTRO: Salut, c’est iAstro !")
            el.ElevenLabsTTS(cfg).synthesize(path, Path(d) / 'out.mp3')
            synth.assert_not_called()
            self.assertEqual(cat.call_args.args[0], [el.APPROVED_IASTRO_GREETING])
            self.assertEqual(len(cat.call_args.args), 2)
        for bad in (SCRIPT.replace('Salut,', 'Bonjour,'),
                    SCRIPT.replace('À très vite !', "C'était iAstro !")):
            with self.assertRaises(ValueError):
                audio.validate_iastro_script(bad)
        with self.assertRaises(ValueError):
            el.approved_iastro_greeting('another-voice')
        with patch.object(el, 'APPROVED_IASTRO_GREETING_SHA256', 'incorrect'):
            with self.assertRaises(ValueError):
                el.approved_iastro_greeting(cfg['voix_iastro_elevenlabs'])

    @unittest.skipUnless(__import__('shutil').which('ffmpeg'), 'ffmpeg required')
    def test_real_mix_accepts_recorded_greeting_and_synthesized_mp3(self):
        import shutil, subprocess
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); tone = root / 'tone.mp3'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'sine=frequency=440:sample_rate=44100', '-t', '1',
                            '-ac', '1', '-c:a', 'libmp3lame', '-b:a', '128k', str(tone)], check=True)
            def synth(text, voice, dest, **kw): shutil.copyfile(tone, dest)
            def dialogue(lines, dest, **kw): shutil.copyfile(tone, dest)
            script = root / 'script.txt'
            script.write_text("IASTRO: Salut, c'est iAstro ! Bienvenue.\nVICTORIA: Bonjour.")
            with patch.object(el, 'tts', side_effect=synth), patch.object(el, 'dialogue', side_effect=dialogue):
                el.ElevenLabsTTS(audio.audio_config()).synthesize(script, root / 'mix.mp3')
            duration = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                'format=duration', '-of', 'default=nw=1:nk=1', str(root / 'mix.mp3')]))
            self.assertGreater(duration, 3.2)
            self.assertLess(duration, 3.8)
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(root / 'mix.mp3'), '-f', 'null', '-'], check=True)

    def test_pitch_preserving_deesser_filter(self):
        with tempfile.TemporaryDirectory() as d, patch.object(el.subprocess, 'run') as run:
            el.concat_mp3([Path(d)/'a.mp3'], Path(d)/'out.mp3', 1.15, deess=True)
            cmd = run.call_args.args[0]
            chain = cmd[cmd.index('-filter:a')+1]
            self.assertIn('atempo=1.15,deesser=i=0.35:m=0.35:f=0.5', chain)
            self.assertNotIn('asetrate', chain)


if __name__ == '__main__':
    unittest.main()
