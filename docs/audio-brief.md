# Brief IA audio — audit et implémentation

Audit du 10 septembre 2026, dépôt `hl-works/veille-ia`, base
`a3db8d017e21ca4a7cd58fb187276d8528168905`. Branche locale :
`feat/daily-audio-brief`. Fonction désactivée par défaut. Aucun déploiement,
changement de secret, envoi Telegram ou service payant créé pendant ce travail.

## Veille existante

- Python 3.12 exécuté dans GitHub Actions (`ubuntu-latest`), sans serveur applicatif
  ni GPU configuré. La collecte quotidienne est dans `veille/main.py`.
- `config.yaml` définit 65 comptes X, 7 flux RSS et 12 chaînes YouTube. X passe
  par twitterapi.io ; les trois autres types de sources utilisent des API/flux publics.
  RSS : Simon Willison, Hugging Face, OpenAI, DeepMind, Google AI, Import AI et MIT.
- Fenêtre glissante de 24 heures, jusqu'à 20 tweets conservés par compte. Les fils
  disponibles d'un auteur sont recollés ; retweets/réponses filtrés ; déduplication
  par identifiant dans la collecte. HN : mots-clés IA, au moins 60 points,
  maximum 60 éléments examinés et 12 conservés. RSS : 4 entrées par flux ;
  YouTube : 3 par chaîne, filtre IA supplémentaire désactivé dans la configuration.
- Deux sorties éditoriales distinctes existent déjà. Pour le site, Claude sélectionne
  des éléments X, ajoute résumé, tags et score 0–100. `feed.json` est cumulatif,
  dédupliqué par URL et `seen.json`. Pour Telegram, X + HN + RSS + YouTube sont
  envoyés au rédacteur ; le regroupement des événements et la sélection sont
  demandés dans le prompt. Il n'existe pas de score numérique ni de mémoire
  persistante de déduplication éditoriale propre au digest Telegram.
- Rédaction via l'API Anthropic, modèle configuré `claude-opus-4-8`, mode détaillé :
  essentiel visible et détails repliables. Ce nom est repris de la configuration,
  sans changement de modèle. L'envoi utilise `sendMessage`, avec découpage HTML
  et réessais réseau/429/5xx.
- Cron : toutes les 20 minutes à :03/:23/:43 de 06 à 09 UTC. Garde horaire
  Europe/Paris à partir de 08:00 et état `.state/last_run.txt`. Les déclenchements
  manuels passent le garde-fou ; groupe de concurrence sans annulation.
  GitHub ne garantit pas l'heure exacte de démarrage.
- Le job committe feed/seen/état puis copie le feed vers `hl-works/knowledge-hub`,
  à `knowledge-hub/veille-ia/feed.json`. Le site a déjà `index.html`, `feed.json`
  et `feed.xml`, avec URL canonique `https://hl-consulting.tech/knowledge-hub/veille-ia/`.
  Pas de stockage du digest Telegram complet ou de lecteur audio dans cette page.
  L'hébergement du bot est établi par le workflow ; l'hébergeur du site public
  n'a pas été vérifié dans cette intervention.
- Autres workflows : enrichissement rétroactif du feed, backfill historique,
  rejeu de digests et commandes Telegram sondées toutes les 5 minutes.
- Secrets déclarés : `ANTHROPIC_API_KEY`, `TWITTERAPI_IO_KEY`,
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID` (alias `TELEGRAM_CHAT_ID` accepté),
  `KH_REPO_TOKEN`, `TELEGRAM_AUTHORIZED_USER_ID` pour les commandes privées.
  Leurs valeurs et leur configuration effective n'ont pas été consultées.
- Les dernières exécutions consultées, dont la veille du 10 septembre à 13:30 UTC,
  sont marquées réussies par GitHub. Cela ne prouve pas que chaque source a répondu
  ou que Telegram a été livré : le code existant tolère plusieurs échecs.

## Limites existantes constatées

RSS et YouTube fournissent surtout le titre et le lien ; HN fournit le titre et
les métriques, sans article complet. Un rédacteur ne peut pas en déduire des
explications détaillées fiables sans autre source. L'audio est strictement invité
à ne rien ajouter au digest, mais cette consigne ne remplace pas une validation
éditoriale à l'écoute. Le prompt ne garantit pas mathématiquement l'absence
absolue d'hallucination.

Le workflow historique marque la journée faite même si Telegram a échoué ou
n'est pas configuré. Ce comportement préexistant n'est pas modifié ici ; dans
ce cas l'audio n'est pas exporté. Le flux du site peut différer du digest :
il serait incorrect de le considérer comme un vrai brief Telegram archivé.

## Insertion retenue

Après retour réussi de `send_message`, export du message exact, de son texte,
de ses liens, de sa date et de son empreinte SHA-256. Aucun appel audio dans le
processus principal. Une exception d'export est absorbée sans impact sur l'écrit.
Un message sans lien source est traité comme une journée calme et n'a pas d'audio.
Cela suppose le respect du contrat actuel du digest : chaque sujet a un lien.

Le workflow transmet cet instantané via un artefact, puis un job indépendant :

1. Adapte seulement le digest final en script oral via le modèle Anthropic existant.
2. Refuse une réponse vide, interrompue ou refusée. La durée n'a pas de cible.
3. Appelle le fournisseur `QwenTTS` derrière l'interface `TTSProvider`.
4. Produit un MP3 mono 24 kHz à 64 kbit/s, mesure sa durée avec ffprobe.
5. Envoie avec `sendAudio` : lecteur natif, titre daté et durée réelle.
6. Conserve MP3, transcription, instantané et page HTML d'écoute pendant 14 jours
   dans les artefacts Actions. Aucun MP3 committé dans Git, aucun nouveau site.

Un échec du job audio est toléré ; il ne bloque ni ne rejoue l'écrit. Timeout
Anthropic : 120 s, zéro réessai SDK ; processus Qwen : 20 min ; job : 35 min.
Ce sont des budgets techniques d'exécution, pas des durées éditoriales cibles.
Le processus TTS est tué si son budget est dépassé, plutôt que laissé en arrière-plan.
La première version ne change pas `/maj` ni le rejeu historique.

Pour éviter un doublon sur timeout d'upload ambigu, pas de réessai automatique de
`sendAudio`. Les réexécutions GitHub (`run_attempt > 1`) génèrent l'artefact sans
renvoyer l'audio. Un nouveau lancement manuel complet est une nouvelle publication,
comme dans le système existant ; l'exactement-une-fois Telegram n'est pas garanti.

## Qwen : choix et contraintes

La documentation officielle prend en charge le français et recommande Python 3.12
avec un environnement isolé. Les exemples optimisés utilisent CUDA/bfloat16 et
FlashAttention ; cela ne signifie pas que 96 Go de RAM sont nécessaires à
l'inférence (ce chiffre concerne la compilation FlashAttention).

Premier candidat : `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`, package `qwen-tts==0.1.1`,
voix `Ryan`, langue explicitement `French`. Modèle ouvert Apache-2.0, aucun
abonnement ElevenLabs. Le 0.6B réduit les besoins pour un premier essai CPU,
mais son temps de génération sur le runner et sa qualité en français restent
à mesurer. Les voix prédéfinies ne comprennent pas de locuteur français natif :
l'accent, les noms de produits et les chiffres doivent être évalués à l'écoute.
Le modèle 1.7B est configurable pour un essai ultérieur, sans promesse de rapidité.

Le worker découpe le script sans perdre de mots, charge le modèle une fois et
écrit le WAV progressivement, puis encode le MP3. Les dépendances lourdes sont
installées uniquement dans le job audio. Aucun GPU, endpoint cloud ou abonnement
n'est provisionné. Si le CPU dépasse le budget, conserver la fonction désactivée
et décider d'un matériel/service GPU après un devis et accord explicite.

Coût supplémentaire à l'activation : un appel Anthropic par brief et le calcul/
stockage Actions selon les quotas du compte. Aucune estimation de facture n'est
présentée sans mesure. L'aperçu effectue une vraie collecte et une vraie rédaction,
avec les coûts à l'usage existants, mais ne publie pas de texte ou d'audio.

## Tester puis activer

Après revue et intégration de la branche :

1. Garder la variable de dépôt `DAILY_AUDIO_BRIEF` absente ou `false`.
2. Actions → Veille IA → Run workflow → cocher `audio_preview`.
   Le workflow génère un vrai brief récent en mode dry-run et son audio, sans
   modifier feed/seen/état et sans publier dans Telegram.
3. Télécharger l'artefact `brief-audio`, ouvrir `index.html` ou `brief.mp3`.
   Vérifier couverture de tous les sujets, neutralité, noms, chiffres, accent,
   transitions et durée de calcul. Comparer avec `brief.json` et `transcript.txt`.
4. Seulement après validation de la voix et du budget, définir
   `DAILY_AUDIO_BRIEF=true`. Le lendemain : écrit, puis audio quand il est prêt.
   Désactivation : remettre `false`, sans toucher aux secrets.

Variables optionnelles : `QWEN_MODEL`, `QWEN_SPEAKER`. `QWEN_DEVICE=cpu` est fixé
pour le runner actuel. Un futur fournisseur implémente `TTSProvider.synthesize` ;
aucun fallback commercial implicite. Un fournisseur inconnu échoue proprement.

En local, dans un environnement audio Python 3.12 isolé avec FFmpeg et SoX :

```bash
pip install -r requirements-audio.txt
# À partir d'un instantané du vrai digest déjà exporté :
python -m veille.audio --snapshot audio-input/brief.json
# --send est nécessaire pour publier ; par défaut c'est un fichier seul.
python -m unittest discover -s tests -v
```

## Validation et état de livraison

10 tests unitaires passent : sélection finale exacte, journée calme, ordre écrit
puis export, isolement des pannes, flag off, dry-run sans envoi, script tronqué,
timeout TTS, découpage sans perte, archive échappée et contrat sendAudio.
YAML de tous les workflows analysé et `git diff --check` sans erreur.
Ces tests utilisent des doubles pour Anthropic, Qwen et Telegram ; ils ne valident
ni une vraie inférence ni la qualité vocale.

Pas de premier MP3 parlé fourni : pas de clés de veille dans la session ni de
modèle Qwen prêt, et aucun digest Telegram final archivé dans le dépôt. Le feed
X n'a pas été présenté abusivement comme un vrai brief Telegram.

Le connecteur GitHub expose `pull=true`, `push=false` sur ce dépôt. La branche et
le patch sont préparés localement ; aucune PR distante ou mise en production n'a
été effectuée. Prochaine étape nécessitant un accès : pousser la branche, ouvrir
une PR, lancer l'aperçu et écouter le premier résultat avant activation.

Sources techniques vérifiées :
- https://github.com/QwenLM/Qwen3-TTS
- https://core.telegram.org/bots/api#sendaudio (MP3/M4A, limite actuelle 50 Mo)
- https://github.com/hl-works/veille-ia/blob/main/.github/workflows/veille.yml
