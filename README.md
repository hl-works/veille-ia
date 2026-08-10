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
   (Twitter ayant fermé ses accès gratuits).
2. **Filtrage** — on enlève le bruit (retweets, réponses, hors fenêtre).
3. **Rédaction** — Claude (`claude-opus-4-8`) regroupe l'info par thème et
   rédige un digest factuel sur **deux niveaux** (mode `detaille`, par défaut) :
   - un **survol visible** — « l'essentiel en 30 s » + une accroche d'une ligne
     par sujet ;
   - sous chaque sujet, un **bloc « détails » repliable** (`<blockquote
     expandable>` : le lecteur le touche pour le dérouler) qui reprend le sujet
     **en entier et 100 % en français** — le fait complet, les chiffres, le
     contexte, le *pourquoi c'est important*. Tout est dans le message Telegram :
     **pas besoin d'ouvrir X**, ça marche **hors ligne**. Les liens sources
     restent en référence, optionnels.
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
| `send_when_empty` | Publier un message même sans actu. |

## Coûts

- **twitterapi.io** : facturé à l'usage (suivre ~10-20 comptes/jour coûte
  quelques centimes).
- **API Claude** : un digest quotidien représente une poignée de centimes.
- **GitHub Actions** : gratuit dans la limite généreuse des dépôts publics.
