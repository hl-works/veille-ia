# Le Podcast IA — raccordement et identité

## Décision du 17 octobre 2026

Une émission, **Le Podcast IA**, par **Hugo LaHutte**, dans l'univers d'**iAstro**.
Le Débrief complet part dans le RSS Spotify/Apple ; Le Flash reste sur le site
et Telegram. L'introduction, la conclusion et les titres Telegram des futurs
audios reprennent ces noms. Les anciens MP3 ne sont pas régénérés.

La voix reste Victoria avec les réglages déjà validés dans `audio.yaml`.
Le présent lot ne lance aucun casting, ne change aucune voix et ne déclenche
aucun envoi supplémentaire. Les garde-fous d'envoi restent en place.

## Flux

`scripts/export-podcast.py` garde son contrôle des deux envois Telegram publics
confirmés. `scripts/push-podcast-site.sh` appelle ensuite le générateur du site
`scripts/build_podcast_feed.py --archive-latest` uniquement si le flux initial
`assets/podcast/feed.xml` est déjà présent dans `knowledge-hub/main`.

Le site maintient les archives datées, les durées, les tailles, les empreintes et
les GUID stables. Le bridge pousse latest, les nouvelles archives, le manifeste
et le RSS dans le même commit. Chaque tentative repart de main dans un clone
temporaire ; aucune erreur du générateur ne doit produire un commit partiel.
Une réexécution du même audio est sans doublon. Un MP3 différent pour une date
déjà archivée provoque un arrêt, sans écraser l'archive distribuée.

Ordre : tester avec une sortie réelle déjà publique sans réseau ni Telegram,
publier le flux initial avec le contact validé, puis déployer le bridge.
Le succès local ou GitHub ne prouve pas la propagation sur les plateformes :
observer le premier épisode puis le suivant avant d'annoncer l'automatisation.

## Future voix iAstro — brief de casting

Intention de Hugo : retrouver l'énergie du personnage Astro en français.
Direction proposée : voix masculine jeune, claire, curieuse et chaleureuse,
français de France, sourire léger, élan et sens de l'émerveillement ; diction
nette des noms techniques, avec un débit qui laisse comprendre les nouvelles.
Éviter l'excès d'aigus, les effets robotiques, le jeu infantilisant et les cris.
Créer une identité vocale propre à iAstro ; ne pas cloner un comédien de doublage.

Préparer trois essais sur le même texte de 20–30 secondes : posé et curieux,
énergique et souriant, complice et légèrement malicieux. Écouter aussi un
passage d'actualité technique avant de choisir. Aucun changement de voix en
production avant écoute et validation de Hugo.

Texte de casting : « Bonjour, c'est iAstro. Bienvenue dans Le Podcast IA.
Aujourd'hui, on prend un peu de recul sur l'intelligence artificielle.
Une annonce peut sembler spectaculaire. Mais ce qui nous intéresse, c'est
ce qu'elle change vraiment dans nos usages. Alors, qu'est-ce qui mérite
ton attention ? On regarde ça ensemble. »

Après choix : conserver le voice_id, les réglages, le fournisseur et les
conditions d'utilisation applicables dans la configuration prévue, puis
tester un aperçu privé. Ne pas annoncer iAstro dans l'audio avant cette étape.
