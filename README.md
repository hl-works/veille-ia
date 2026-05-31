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
   rédige un digest court, factuel, avec les liens des tweets sources.
4. **Publication** — le digest est envoyé sur ton canal Telegram.

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

## Structure du projet

```
veille-ia/
├── config.yaml              ← les comptes à suivre + réglages (à éditer)
├── requirements.txt
├── .env.example             ← modèle pour tester en local
├── veille/
│   ├── config.py            ← chargement config + secrets
│   ├── twitter.py           ← récupération des tweets (twitterapi.io)
│   ├── digest.py            ← rédaction du digest (Claude)
│   ├── telegram.py          ← publication sur Telegram
│   └── main.py              ← orchestration
└── .github/workflows/
    └── veille.yml           ← le cron quotidien
```

## Réglages utiles (`config.yaml`)

| Champ | Rôle |
|---|---|
| `accounts` | Les comptes Twitter/X suivis (sans `@`). |
| `lookback_hours` | Fenêtre de récupération (24 = la dernière journée). |
| `max_tweets_per_account` | Plafond de tweets récupérés par compte. |
| `include_retweets` / `include_replies` | Inclure ou non retweets/réponses. |
| `model` | Modèle Claude (`claude-opus-4-8`, ou `claude-sonnet-4-6` pour réduire le coût). |
| `send_when_empty` | Publier un message même sans actu. |

## Coûts

- **twitterapi.io** : facturé à l'usage (suivre ~10-20 comptes/jour coûte
  quelques centimes).
- **API Claude** : un digest quotidien représente une poignée de centimes.
- **GitHub Actions** : gratuit dans la limite généreuse des dépôts publics.
