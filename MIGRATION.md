# Migration — ce dépôt devient le moteur de l'usine à veilles

> À lire avant de coder ici. Décidé le 19/08/2026.

## La cible

Un seul dépôt **`veille`**, un moteur, **N sujets**. Ajouter une veille = ajouter
un dossier, pas forker un dépôt.

```
veille/
├── engine/                  ← ne connaît ni « IA » ni « hifi »
│   ├── sources/             ← x.py, hackernews.py, rss.py, youtube.py
│   │                          interface uniforme : fetch(fenêtre) -> [Item]
│   ├── pipeline.py          ← collecte → filtre → dédup → rédige → publie
│   ├── digest.py  feed.py
│   └── publish.py           ← délègue au socle pour Telegram
├── profiles/
│   ├── ia/    config.yaml + prompt.md + state/seen.json
│   ├── hifi/  idem
│   └── _template/           ← nouveau sujet = cp -r, ~20 min
└── .github/workflows/veille.yml   ← matrix sur profiles/*, fail-fast: false
```

**C'est le moteur de ce dépôt qui part dans `engine/`.** `veille/` ici est déjà
découpé proprement — `sources.py`, `feed.py`, `digest.py`, `enrich.py`,
`twitter.py`, `config.py`, `main.py`, `replay.py`, `backfill.py`. C'est la bonne
base.

## `veille-hifi` n'est pas un jumeau

Contrairement à ce qu'on supposait, `hl-works/veille-hifi` n'est **pas** ce même
moteur avec d'autres comptes. C'est un **monolithe d'un seul fichier** —
`veille_hifi.py`, 36 054 o — créé le 07/03/2026, soit avant ce dépôt (31/05).
Son README fait 13 octets, et son `seen_news.json` (63 Ko) est versionné à la
racine.

Autrement dit : ce dépôt **est** la réécriture modulaire, `veille-hifi` est
l'ancêtre. La migration n'est donc pas une fusion de deux moteurs — c'est
**garder celui-ci et porter le monolithe hifi en profil**. Beaucoup plus simple.

## Le contrat de profil

C'est **le** livrable de la migration. S'il est propre, ajouter « veille
réglementaire » ou « veille voitures anciennes » ne touche pas une ligne du moteur.

Un profil déclare :

| Élément | Rôle |
|---|---|
| `config.yaml` | sources activées et leurs paramètres, seuils, budget, horaire |
| `prompt.md` | la ligne éditoriale — **le produit** |
| `outputs` | canal Telegram, dépôt et chemin du `feed.json` |
| `state/seen.json` | mémoire de dédup, **propre au profil** |

Le moteur ne doit **jamais** contenir le mot « IA » ni « hifi ».

## Ce qu'on n'industrialise pas

**La ligne éditoriale.** Un prompt générique sur N domaines donne N digests mous.
`prompt.md` reste par profil.

**Les sorties.** Deux veilles = deux bots, deux canaux, deux `feed.json`, deux
sites. Les audiences n'ont rien à voir. On fusionne le moteur, jamais la sortie.

## Pièges

- **`seen.json` strictement par profil.** Un fichier commun ferait disparaître
  silencieusement un sujet d'un feed parce que l'autre l'a déjà vu.
- **`fail-fast: false`** sur la matrix, sinon un profil cassé prive tous les
  autres de leur digest du matin.
- **Plafond de budget par profil** sur les sources payantes, sinon la 5ᵉ veille
  fait exploser la note.
- **Secrets suffixés par profil** (`TELEGRAM_CHAT_ID_IA`, `_HIFI`, …).
- **Copyright** : jamais de contenu source recopié mot pour mot — résumé ou
  traduction FR (notre texte) + lien source.

## ⚠️ À ne pas faire d'ici là

**Ne rien investir dans `veille/telegram.py` et `veille/listen.py`.**

Il existe aujourd'hui **douze implémentations** de « poster sur Telegram » dans le
parc HL, dont ces deux-ci. Elles seront remplacées par le socle (`agent-core`).
Toute heure passée à les améliorer produit la treizième implémentation à jeter.

Seule exception, et elle va dans l'autre sens : **le filtre sur
`TELEGRAM_AUTHORIZED_USER_ID` de `listen.py` est le bon réflexe**, et il manque
cruellement à `hl-works/agent` (`mail/agent_loop.py` n'a **aucun** contrôle du
`chat_id` entrant : quiconque écrit au bot déclenche les commandes). C'est un cas
où c'est ce dépôt qui doit alimenter les autres.

## À vérifier avant de porter quoi que ce soit

Le token fine-grained `veille-ia → knowledge-hub` est marqué **« Never used »**
côté GitHub. Si c'est exact, le pont `feed.json` vers le site **n'a jamais
tourné** — le README le dit à demi-mot : l'étape de push est sautée en silence si
`KH_REPO_TOKEN` n'est pas défini. À confirmer côté `knowledge-hub` avant de
reproduire ce pont dans l'usine.

## Ordre des travaux

1. Créer `hl-works/veille`, y déposer le moteur d'ici **tel quel** + profil `ia`
2. 3 jours de dry-run en parallèle de l'existant, digests comparés
3. Lire `veille-hifi/veille_hifi.py` et en extraire ce qui est **métier**
   (sources, comptes suivis, ligne éditoriale) → profil `hifi`
4. Vérifier le pont `feed.json`
5. Bascule des crons, archivage de `veille-ia` et `veille-hifi`
6. `_template/` + la doc
7. **Ensuite seulement** : remplacer la couche Telegram par le socle
