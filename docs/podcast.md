# Podcast IA quotidien — état au 25/09/2026

**Généré chaque matin, jamais publié sans validation.** Aucun envoi Telegram
tant que la variable de dépôt `AUDIO_SEND` n'est pas à `true` (décision d'Hugo,
après écoute). Le MP3 et la transcription restent dans l'artefact `brief-audio`.
Pipeline actif dès que `.github/workflows/veille.yml` est remplacé par
`ci/veille.yml` (voir plus bas). Après le digest écrit, le job `audio` adapte le
digest publié (et rien d'autre) en script oral, le fait lire, et envoie le MP3
dans Telegram. Un échec audio n'affecte jamais l'écrit.

Réglages par défaut (dans `veille/audio.py` → `DEFAULT_AUDIO`), surchargeables
par un bloc `audio:` dans `config.yaml` ou les variables de dépôt `AUDIO_*` :

| Champ | Défaut | Rôle |
|---|---|---|
| `provider` | `edge` | voix neuronales Microsoft (gratuites, sans clé) · `qwen` = modèle ouvert, lent sur CPU |
| `format` | `solo` | une voix féminine neutre · `duo` = dialogue femme + homme (répliques ELLE:/LUI:) |
| `destination` | `prive` | MP à Hugo (`TELEGRAM_AUTHORIZED_USER_ID`) · `canal` = canal public |
| `voix_femme` | `fr-FR-VivienneMultilingualNeural` | alternative : `fr-FR-DeniseNeural` |
| `voix_homme` | `fr-FR-RemyMultilingualNeural` | alternative : `fr-FR-HenriNeural` |

**Règles de voix (Hugo, 25/09) :** accent de France uniquement — jamais de voix
canadienne (ni belge/suisse) : seules les voix `fr-FR-*` sont admises. La voix
libre Kokoro `ff_siwis` testée le 25/09 est écartée (perçue comme canadienne).
Prononciation : français avec une légère touche d'anglais sur les marques
anglaises, pas plus — voir `lexique.yaml` (validé).

Couper : variable de dépôt `DAILY_AUDIO_BRIEF=false`. Tester sans publier :
Actions → Veille IA → Run workflow → `audio_preview` → artefact `brief-audio`.

Limite `edge` : service Microsoft non officiel (`edge-tts`), sans licence
commerciale explicite — OK en interne. Pour un vrai podcast public, brancher un
service sous licence (ElevenLabs, Google, OpenAI) derrière `TTSProvider`.

## Heure de publication

Les crons GitHub partaient avec 3 à 5 h de retard (digest reçu 13h-14h40 tout
septembre). Déclencheur principal désormais : un push sur `.state/tick`, écrit
chaque matin à 08:10 Europe/Paris par une tâche planifiée Claude. Crons conservés
en filet de sécurité ; `.state/last_run.txt` garantit un seul digest par jour.

## Mise en service (une fois)

L'intégration GitHub de Claude n'a pas le droit d'écrire dans
`.github/workflows/`. Il faut donc, depuis un compte humain :

```bash
cp ci/veille.yml .github/workflows/veille.yml && git rm -q ci/veille.yml
git commit -am "ci: départ 8h10 via .state/tick + podcast" && git push
```

## Accueil HL Consulting (octobre 2026)

Après un envoi public réussi des deux formats sur Telegram, le job audio copie
`court.mp3` et `brief.mp3` vers `knowledge-hub/assets/podcast/`, avec un manifeste
`latest.json` limité à la date, aux durées et aux chemins publics. Le secret
`KH_REPO_TOKEN`, déjà utilisé par le brief écrit, permet ce bridge.

La home lit ce manifeste à chaque visite. Les MP3 ne chargent qu'au lancement
volontaire de la lecture. Seule la dernière paire est présente dans l'arbre du
site ; la branche interne `ecoute` conserve les archives. Un aperçu privé, un
épisode incomplet ou un ancien run ne remplace jamais la paire courante. Si le
bridge échoue, le dernier épisode reste écoutable avec sa date d'origine.

Vérification ciblée : `python -m unittest discover -s tests -p test_podcast_site.py`.
