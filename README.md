# 🤖 Veille IA

Un bot qui surveille des comptes **Twitter/X**, demande à **Claude** d'en
rédiger un **digest** clair, et le publie chaque matin sur un **canal
Telegram**. Tourne tout seul via **GitHub Actions** — aucun serveur à gérer.

```
Comptes Twitter/X  →  twitterapi.io  →  Claude rédige le digest  →  Telegram
        (config.yaml)                       (API Claude)            (canal public)
                          ⏰ déclenché chaque matin par GitHub Actions
```

## Comment ça marche

1. **Récupération** — pour chaque compte de `config.yaml`, on récupère les
   tweets des dernières 24 h via [twitterapi.io](https://twitterapi.io)
   (Twitter ayant fermé ses accès gratuits). En plus de X, le digest peut être
   enrichi par d'**autres sources** (voir plus bas) : **Hacker News** (les
   meilleures actus IA), les **blogs officiels via RSS** (OpenAI, DeepMind,
   Hugging Face…) et **YouTube** (nouvelles vidéos de chaînes suivies) — le tout
   **gratuit et sans clé**. Ces sources n'alimentent que le digest Telegram —
   **pas `feed.json`** (le site reste inchangé).
2. **Filtrage** — on enlève le bruit (retweets, réponses à d'autres comptes,
   hors fenêtre). Les **fils d'un même auteur** (plusieurs tweets qui se suivent)
   sont **recollés en un seul contenu** : rien du propos n'est perdu, sans pour
   autant ramasser la conversation des autres.
3. **Rédaction** — Claude (`claude-opus-4-8`) regroupe l'info par thème et
   rédige un digest factuel sur **deux niveaux** (mode `detaille`, par défaut) :
   - **« 📌 L'essentiel du jour »** — le corps visible, pensé pour **1 à 2 minutes
     de lecture** : chaque sujet a 2 à 4 phrases directement lisibles ;
   - sous chaque sujet, un **bloc « détails » repliable** (`<blockquote
     expandable>` : le lecteur le touche pour le dérouler) qui reprend le sujet
     **en entier et 100 % en français** — tout le contenu (y compris les **fils**
     complets), les chiffres, le contexte, le *pourquoi c'est important*. Tout est
     dans le message Telegram : **pas besoin d'ouvrir X**, ça marche **hors ligne**.
     Les liens sources restent en référence, optionnels.
4. **Publication** — le digest est envoyé sur ton canal Telegram.

> 🔎 **Digest court ou développé ?** Règle `digest_depth` dans `config.yaml` :
> `detaille` (défaut, survol + détails repliables FR, lecture autonome hors
> ligne) ou `essentiel` (survol rapide sans blocs repliables, moins de tokens).

## Mise en route

### 1. Les quatre secrets dont tu as besoin

| Secret | Où l'obtenir |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) → API Keys |
| `TWITTERAPI_IO_KEY` | [twitterapi.io](https://twitterapi.io) → crée un compte, copie ta clé (facturée à l'usage, quelques centimes/jour) |
| `TELEGRAM_BOT_TOKEN` | Sur Telegram, écris à [@BotFather](https://t.me/BotFather) → `/newbot` → il te donne le token |
| `TELEGRAM_CHAT_ID` | L'identifiant de ton canal : `@mon_canal` (public) ou un nombre négatif (privé) |

> 💡 **Créer le canal Telegram :** crée un canal, ajoute ton bot comme
> **administrateur** (sinon il ne peut pas publier). Pour un canal public,
> `TELEGRAM_CHAT_ID` = `@nom_du_canal`. Pour un canal privé, récupère son ID
> numérique (ex. via [@userinfobot](https://t.me/userinfobot) ou l'API).

### 2. Configurer les comptes suivis

Édite **`config.yaml`** : ajoute/retire les comptes Twitter dans `accounts`
(sans le `@`). Tu peux aussi régler la fenêtre temporelle, les filtres, etc.

### 3. Lancer automatiquement (GitHub Actions)

1. Pousse ce dépôt sur GitHub.
2. Dans **Settings → Secrets and variables → Actions**, ajoute les quatre
   secrets ci-dessus (bouton *New repository secret*).
3. C'est tout : le bot tourne chaque matin (06:00 UTC). Tu peux aussi le
   lancer à la main depuis l'onglet **Actions → Veille IA → Run workflow**.

Pour changer l'heure, modifie le `cron` dans
[`.github/workflows/veille.yml`](.github/workflows/veille.yml).

## Tester en local

```bash
pip install -r requirements.txt

# Renseigne tes clés
cp .env.example .env        # puis édite .env
export $(grep -v '^#' .env | xargs)

# Aperçu du digest SANS publier sur Telegram (ne touche pas à ton canal)
python -m veille.main --dry-run

# Exécution réelle (publie sur Telegram)
python -m veille.main
```

Le mode `--dry-run` n'a même pas besoin des secrets Telegram : il affiche
juste le digest qui *serait* publié.

## Rejouer les derniers jours sur Telegram (nouveau format)

Pour « rattraper » le canal avec le format détaillé sans attendre le cron, le
module `replay` régénère un digest **par jour** sur les N derniers jours et le
**publie en nouveaux messages** (datés, du plus ancien au plus récent). Il ne
modifie pas les anciens messages et ne touche ni à `feed.json` ni à `seen.json`.

```bash
# Aperçu du DERNIER jour (rien n'est publié) — le test recommandé :
python -m veille.replay --dry-run

# Publier le dernier jour, puis la semaine :
python -m veille.replay --days 1
python -m veille.replay --days 7
```

Ou, sans terminal : onglet **Actions → « Rejeu digest Telegram » → Run workflow**,
règle `days` (1 pour tester, 7 pour la semaine) et `dry_run` (coché = aperçu dans
les logs, décoché = publie vraiment). ⚠️ Consomme du budget twitterapi.io
(plafonds par compte/jour intégrés).

### Menu Telegram : lancer la MAJ depuis le bot (sans passer par GitHub)

Tu peux déclencher le rejeu en écrivant directement au bot, en **message privé** :

| Commande | Effet |
|---|---|
| `/maj` | republie **hier** (jour complet) au nouveau format |
| `/maj 7` | republie les **7 derniers jours complets** (max 14) |
| `/aide` | rappelle les commandes |

> La **journée en cours** n'est pas rejouée : la recherche historique est peu
> fiable sur les toutes dernières heures, et ce jour est de toute façon déjà
> couvert par le digest automatique de 7h.

Comment ça marche (sans serveur) : le workflow **« Commandes Telegram »**
(`.github/workflows/telegram-commands.yml`) **sonde** Telegram toutes les ~5 min
et exécute la commande. Compte donc **~5-15 min de latence** (GitHub peut retarder
les crons courts) ; tu peux aussi lancer ce workflow à la main pour traiter tout
de suite. Le bot t'accuse réception (« ⏳ lancé… » puis « ✅ terminé »).

**Activation (une seule fois) :**
1. Écris `/start` au bot en privé (pour qu'il puisse te répondre).
2. Récupère ton **ID Telegram numérique** via [@userinfobot](https://t.me/userinfobot).
3. Ajoute-le en secret du dépôt : **Settings → Secrets and variables → Actions →
   New repository secret**, nom `TELEGRAM_AUTHORIZED_USER_ID`, valeur = ton ID.

> 🔒 Sans ce secret, **aucune** commande n'est exécutée. Et seule **ta** commande
> (ton ID) est acceptée : personne d'autre ne peut déclencher de coûts.

## Deux sorties à partir de la même collecte

À chaque run, le bot produit :

1. **Digest Telegram** (push quotidien ~7h) — résumé thématique sur le canal.
2. **`feed.json`** — donnée structurée que le **site** (`knowledge-hub`) consomme.
   Cumulatif : chaque run *append* les nouveaux sujets marquants sans réécrire,
   en dédupliquant via `seen.json`.

### Contrat `feed.json`

Tableau d'entrées, une par sujet marquant (jour creux = aucune entrée) :

```json
[
  {
    "date": "2026-05-19",
    "titre_fr": "Titre court factuel",
    "resume_fr": "Résumé FR neutre, transformatif (jamais de recopie du tweet).",
    "tags": ["anthropic", "talents"],
    "tweet_url": "https://x.com/.../status/...",
    "media": true,
    "auteur_x": "@..."
  }
]
```

> **Copyright (règle dure)** : jamais de tweet recopié mot pour mot. Toujours
> résumé / traduction FR (notre texte) + lien source.

### Backfill (contenu de lancement)

Pour générer un `feed.json` initial couvrant une période passée (mai 2026) :

```bash
# Aperçu sans rien écrire (borné à 600 tweets par défaut) :
python -m veille.backfill

# Génère réellement feed.json + seen.json :
python -m veille.backfill --write
```

Ou via GitHub : onglet **Actions → Backfill feed.json → Run workflow** (coche
« Écrire feed.json »). ⚠️ Consomme du budget twitterapi.io — plafond strict.

### Bridge vers le site (`knowledge-hub`)

Le run pousse `feed.json` dans le repo du site **uniquement si** le secret
`KH_REPO_TOKEN` est défini (un token avec accès en écriture à `knowledge-hub`).
Tant qu'il n'existe pas, l'étape est silencieusement sautée et `feed.json` reste
versionné dans ce repo. Ajuste `KH_REPO` / `KH_FEED_PATH` dans
`.github/workflows/veille.yml` au repo et chemin réels du site.

## Structure du projet

```
veille-ia/
├── config.yaml              ← les comptes à suivre + réglages (à éditer)
├── requirements.txt
├── .env.example             ← modèle pour tester en local
├── feed.json                ← donnée structurée pour le site (généré, cumulatif)
├── seen.json                ← mémoire des tweets déjà traités (dédup)
├── veille/
│   ├── config.py            ← chargement config + secrets
│   ├── twitter.py           ← récupération des tweets + advanced_search (backfill)
│   ├── digest.py            ← rédaction du digest Telegram (Claude)
│   ├── feed.py              ← génération feed.json structuré (Claude) + dédup
│   ├── telegram.py          ← publication sur Telegram
│   ├── backfill.py          ← génération one-shot du feed.json initial
│   └── main.py              ← orchestration (Telegram + feed.json)
└── .github/workflows/
    ├── veille.yml           ← le cron quotidien (Telegram + feed.json + bridge)
    └── backfill.yml         ← backfill manuel
```

## Réglages utiles (`config.yaml`)

| Champ | Rôle |
|---|---|
| `accounts` | Les comptes Twitter/X suivis (sans `@`). |
| `lookback_hours` | Fenêtre de récupération (24 = la dernière journée). |
| `max_tweets_per_account` | Plafond de tweets récupérés par compte. |
| `include_retweets` / `include_replies` | Inclure ou non retweets/réponses. |
| `model` | Modèle Claude (`claude-opus-4-8`, ou `claude-sonnet-4-6` pour réduire le coût). |
| `digest_depth` | `detaille` (défaut, lecture autonome hors ligne) ou `essentiel` (survol court). |
| `sources.hacker_news` | Inclure les meilleures actus IA de Hacker News (gratuit, sans clé). |
| `sources.hacker_news_min_score` | Score minimum (points HN) pour retenir une actu. |
| `sources.rss` | Inclure les billets récents des blogs officiels (via `rss_feeds`). |
| `rss_feeds` | Liste des flux RSS suivis (un flux mort est ignoré, jamais bloquant). |
| `sources.youtube` | Inclure les nouvelles vidéos des chaînes de `youtube_channels`. |
| `sources.youtube_ai_filter` | `true` = ne garder que les vidéos au titre « IA » (pour chaînes généralistes). |
| `youtube_channels` | Chaînes suivies : ID `UC…` **ou** handle/URL `@MaChaine` (l'ID est résolu tout seul). |
| `send_when_empty` | Publier un message même sans actu. |

> 🔌 **Sources en plus de X.** Hacker News et les flux RSS **enrichissent le
> digest Telegram uniquement** (jamais `feed.json`). Le digest croise les
> sources : un événement rapporté par X **+** Hacker News **+** le blog officiel
> est regroupé en un seul sujet et jugé plus fiable. Édite `rss_feeds` librement.

## Coûts

- **twitterapi.io** : facturé à l'usage (suivre ~10-20 comptes/jour coûte
  quelques centimes).
- **API Claude** : un digest quotidien représente une poignée de centimes.
- **GitHub Actions** : gratuit dans la limite généreuse des dépôts publics.
