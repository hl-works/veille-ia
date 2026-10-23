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

## Répartition validée le 17 octobre 2026

Le Flash et le Débrief utilisent `format: iastro`. iAstro ouvre, introduit
chaque sujet et conclut ; Victoria conserve toutes les informations et les
explications. Les deux voix s'enchaînent directement, sans annoncer Victoria.
Chaque réplique porte un rôle `IASTRO:` ou `VICTORIA:` non prononcé. Les rôles
et la structure sont vérifiés avant la synthèse ; les jingles restent entre
les grands sujets.

iAstro utilise Philippine - Animation Creator (`Yx2a8qp2EqI9c5i8MzBo`),
Eleven v4, français, stabilité 0,5 et similarité 0,75. Son débit est accéléré
de 15 % avec `atempo`, sans transposition, et ses sifflantes sont atténuées
(`deesser=i=0.35:m=0.35:f=0.5`). Victoria conserve son moteur Text to Dialogue,
sa voix et son débit. Le nom reste écrit `iAstro` dans une phrase complète.
Interprétation garçon, vive et malicieuse, jamais bébé. Les légères inflexions
canadiennes résiduelles ont été entendues et acceptées par Hugo.

Les épisodes du 17 octobre ont aussi été remontés avec les prises approuvées,
en conservant l'enregistrement Victoria. Leur correction sur le site et le
RSS n'appelle aucun nouvel envoi Telegram.

## Incident du 18 octobre 2026

Le brief écrit a été envoyé, puis la rédaction du script audio a reçu une
réponse Anthropic HTTP 529 à 08:17 Paris. Aucun MP3 n'a été généré et aucun
audio n'a été envoyé. Le job audio était marqué facultatif, d'où un statut
global trompeur de réussite. Le RSS est resté au 17 octobre.

La rédaction du script réessaie désormais uniquement les erreurs transitoires
(réseau, 429, 5xx), jusqu'à quatre tentatives avec pauses de 5, 15 et 45 secondes.
Les erreurs permanentes restent bloquantes. Le job audio et l'export du site
ne masquent plus leurs échecs. La veille écrite reste indépendante et n'est
pas rejouée. Aucun nouvel essai automatique d'envoi Telegram n'est ajouté.

`Podcast recovery preview` récupère l'artefact `audio-input` d'une exécution,
contrôle sa date et l'empreinte du brief, puis prépare les deux pistes sans
identifiants Telegram ni droit d'écriture. Il ne publie ni sur le site ni
sur le canal. Son artefact permet une écoute avant un éventuel rattrapage.

## Prononciation stable d'iAstro — 23 octobre 2026

La synthèse du Débrief du 23 a prononcé le début du nom à l'anglaise malgré
`language_code: fr`. Le nom ne doit plus dépendre d'une nouvelle interprétation
à chaque épisode. L'ouverture utilise la phrase entière « Salut, c'est iAstro ! »
extraite du montage du 17 approuvé par Hugo. Sa provenance, son intervalle et
son empreinte sont dans `audio/iastro-salutation-fr-v1.json`.

Le fichier est déjà accéléré de 15 % avec les sifflantes atténuées ; ces filtres
ne lui sont pas appliqués une deuxième fois. La suite de l'introduction et les
transitions continuent à être générées avec Philippine, la narration avec Victoria.
Le nom est écrit iAstro dans les transcriptions et n'est prononcé qu'une fois,
dans cette salutation fixe. Aucun fragment de nom n'est assemblé séparément.
Une salutation différente ou un nom répété est corrigé avant la synthèse par
la procédure existante de réparation du script ; la validation reste bloquante.
