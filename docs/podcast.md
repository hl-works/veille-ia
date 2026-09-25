# Podcast IA quotidien — état au 25/09/2026

**Actif par défaut** dès que `.github/workflows/veille.yml` est remplacé par
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
