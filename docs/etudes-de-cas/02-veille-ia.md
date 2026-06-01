# Étude de cas — Bot de veille IA : de l'idée à la prod

> **Build in public.** Un agent qui récupère l'actu IA, la fait résumer par
> l'API Claude, et la publie en deux endroits (Telegram + page « Veille IA » du
> site) — le tout sans serveur, orchestré par GitHub Actions. Construit avec
> Claude Code par un non-développeur.

```
Comptes X/Twitter ─┐
                   ├─► twitterapi.io ─► API Claude (résumé FR) ─┬─► Telegram (push quotidien)
RSS (feeds.txt) ───┘                                            └─► feed.json ─► site (archive)
                          ⏰ déclenché chaque matin par GitHub Actions
```

## 1. Le déclic / le besoin de départ

Je voulais **suivre l'actualité IA** (labos, modèles, outils, recherche) **sans y
passer du temps ni me noyer dans le hype**. Avec un angle qui m'est propre :
couvrir l'IA globale **et surtout l'IA utile aux marchands / dirigeants** — le
concret pour une boîte.

Un cas réel m'avait déjà mis sur la piste : **un LLM me rédige chaque matin une
revue de presse hi-fi** à partir d'une trentaine de sources. La veille IA, c'est
la **généralisation** de cette mécanique.

Double finalité dès le départ :

- un **canal Telegram** ([t.me/VeilleIA_HL](https://t.me/VeilleIA_HL)) — push
  quotidien, éphémère ;
- une **archive publique sur le site** (page « Veille IA ») — permanente,
  optimisée SEO/GEO, citable par les IA.

## 2. L'idée → le cadrage (décisions, alternatives écartées)

| Décision | Pourquoi | Alternative écartée |
|---|---|---|
| **Deux repos séparés** (`veille-ia` = moteur, `knowledge-hub` = site) | **Isoler les secrets** (clés API, token bot) du site public | Tout mettre dans le repo du site → secrets exposés |
| **Bot = moteur de données / Site = affichage**, reliés par un seul `feed.json` | Séparation des responsabilités | Le site qui collecte/résume lui-même |
| **Lecture de `feed.json` au runtime** (fetch navigateur), pas au build | Site HTML pur sans build : un push de `feed.json` se reflète sans redéploiement | Régénérer le site à chaque màj |
| **Page archive ≠ Telegram** | L'archive est permanente ; Telegram est éphémère | Compter sur le seul historique Telegram |
| **Renommage « Flux IA » → « Veille IA »** + URL `/veille-ia/` (redirection depuis `/flux-ia/`) | Terme métier plus juste, cohérent repo/canal, meilleur ancrage SEO/GEO | « Flux IA », « Radar IA » |
| **Média des tweets : embed X officiel + repli automatique vignette+lien** | Les embeds X sont fragiles (visiteur non connecté) → l'utilisateur n'est jamais bloqué | Embed seul (casse souvent) |
| **Résumés FR transformatifs, jamais le tweet recopié** | Règle copyright **dure** | Recopier le tweet (interdit) |

> **À préciser (arbitrage non figé) :** la catégorisation. Au départ 2 axes côté
> site (biz / global) ; le modèle a finalement été **piloté par tags** dans le
> schéma `feed.json`. Hugo : confirme si on reste tags-only ou si on réintroduit
> 2 catégories.

## 3. Le « vibe coding » : comment ça s'est construit, étape par étape

Le projet s'est fait en deux temps : **un cadrage en chat** (les décisions
ci-dessus, formalisées dans des MD de handoff), puis **la construction réelle du
code avec Claude Code** dans le repo `veille-ia`.

Le pipeline construit (`veille/`) :

1. **`twitter.py`** — récupère les tweets récents par compte via twitterapi.io
   (+ `advanced_search` pour le backfill).
2. **Filtrage** — retire le bruit (retweets, réponses, hors fenêtre).
3. **`feed.py`** — Claude (rôle « rédac-chef neutre, anti-hype ») **sélectionne
   les sujets marquants** et produit des entrées structurées via **JSON Schema
   imposé** (structured outputs). Les champs **factuels** (URL, date, média,
   auteur) ne sont **pas** confiés à Claude : ils sont relus depuis le tweet
   source par son index `[n]`.
4. **`digest.py`** — rédige le digest Telegram.
5. **`telegram.py`** — publie (avec découpage des messages > 4096 caractères).
6. **`main.py`** — orchestre les **deux sorties** depuis la **même collecte**.
7. **`backfill.py`** — génère le `feed.json` initial (mai 2026), borné en budget.

Le tout tourne **sans serveur** : deux workflows **GitHub Actions**
(`veille.yml` quotidien à 05:00 UTC ≈ 7h Paris, et `backfill.yml` manuel).

## 4. La stack + les outils

- **[twitterapi.io](https://twitterapi.io)** — collecte des tweets (Twitter
  ayant fermé ses accès gratuits). Facturé à l'usage, quelques centimes/jour.
  Clé `<TWITTERAPI_IO_KEY>`.
- **RSS** (`feeds.txt`) — sources complémentaires hors X.
- **[API Claude (Anthropic)](https://console.anthropic.com)** — sélection
  éditoriale + résumés FR neutres. Modèle `claude-opus-4-8` (réglable sur
  `claude-sonnet-4-6` pour réduire le coût). Clé `<ANTHROPIC_API_KEY>`.
- **[Telegram Bot API](https://core.telegram.org/bots/api)** — push du digest.
  Token `<TELEGRAM_BOT_TOKEN>`, canal `t.me/VeilleIA_HL`.
- **[GitHub Actions](https://docs.github.com/actions)** — le planificateur
  (1 run/jour) qui orchestre collecte → résumé → 2 sorties.
- **[GitHub](https://github.com)** (`veille-ia`) — moteur + secrets.
- **[GitHub Pages](https://pages.github.com)** (`knowledge-hub`) — le site.
- **`feed.json`** — le **contrat de données** entre les deux repos (cumulatif).
- **`seen.json`** — la mémoire de **déduplication**.
- **Bridge cross-repo** — en fin de job, `veille-ia` committe/pousse `feed.json`
  dans `knowledge-hub` via un **PAT dédié** `<KH_REPO_TOKEN>`.

> 🔒 **Jamais de secret publié.** Tous les jetons ci-dessus sont des
> placeholders. Ils vivent dans les *Secrets* du repo privé `veille-ia` ; le site
> public n'en contient aucun ; le PAT cross-repo est dédié, à portée limitée,
> jamais réutilisé d'un autre usage.

## 5. Les galères (ce qui a cassé et comment on a réglé)

> Reconstruites fidèlement depuis le code + l'historique Git du repo.

- **Le bridge cross-repo qui se battait avec lui-même.** Premier réflexe :
  `rebase` avant de pousser `feed.json` dans le site. Résultat → **conflits
  `add/add`**. → Notre `feed.json` étant la **source de vérité** (fichier
  cumulatif complet généré côté `veille-ia`), on **écrase** la version du site au
  lieu de fusionner : `git reset --hard origin/main` puis copie + push, avec
  **3 tentatives** de resynchronisation si une autre source a poussé entre-temps.
  *(commits `7cf2157` → `ec80ca4`)*
- **Telegram qui bloquait tout.** Si le bot n'est pas admin du canal (erreur
  `403 "bot is not a member"`) ou en cas de pépin réseau, **toute la livraison
  tombait** — y compris le `feed.json` du site. → Envoi Telegram **rendu
  non-bloquant** (`try/except` qui logue et continue) **et optionnel** : pas de
  Telegram configuré → on saute la publication mais on produit quand même le
  feed. *(commits `500a8ce`, `e9717d1`)*
- **Le nom de secret qui ne collait pas.** Le code attendait `TELEGRAM_CHAT_ID`,
  le secret côté repo s'appelait `TELEGRAM_CHANNEL_ID`. → **Alias** accepté des
  deux côtés. *(commit `e9717d1`)*
- **Workflow GitHub Actions invalide.** J'avais mis un `secrets.*` dans un `if:`
  d'étape — **GitHub interdit le contexte `secrets` dans un `if:`**, le workflow
  ne se validait plus. → Le garde-fou « token absent → on saute » a été déplacé
  **dans le script** (test `[ -z "$KH_REPO_TOKEN" ]`). *(commit `ba581b3`)*
- **Backfill déséquilibré.** Sans quota, quelques comptes bavards mangeaient tout
  le budget de collecte. → **Quota par compte** pour une collecte équitable entre
  les ~45 comptes, + **garde-fou global strict** sur le nombre total de tweets.
  *(commit `00afa3f`)*

## 6. Temps passé (réel) et tokens / coût

**Temps**

- **Cadrage** (architecture 2 repos, contrat `feed.json`, stack, garde-fous) :
  étalé sur **plusieurs courts échanges** avant la construction, formalisé dans
  deux MD de handoff.
- **Mise en route le 31 mai 2026** (comptes + secrets), d'après l'horodatage de
  mes captures :
  - ~15h14–15h19 : compte twitterapi.io + 1ᵉʳ secret.
  - ~18h44–18h50 : bot Telegram (BotFather) + 3 secrets.
  - ~23h42–23h43 : 4ᵉ secret + écran « pas encore de workflow ».
  - **Amplitude ~8h30** sur la soirée — mais ce sont des **écarts d'horloge entre
    captures, pas du temps de travail effectif** (entre les blocs, je faisais
    autre chose). Le **travail réel est nettement plus court**.

> 🔧 **À confirmer par Hugo :** le chiffre publiable que tu assumes. Proposition
> défendable : *« cadrage + mise en route étalés sur une soirée (~8h30
> d'amplitude le 31 mai), pour un temps de travail effectif bien moindre. »*

**Coût** (contrairement au site, ici on paie à l'usage)

- **twitterapi.io** : ~quelques centimes/jour pour suivre ~45 comptes.
- **API Claude** : un digest quotidien = une poignée de centimes. `claude-opus-4-8`
  par défaut ; `claude-sonnet-4-6` pour réduire encore.
- **GitHub Actions** : gratuit dans la limite des dépôts publics.
- **Garde-fous budget** (« leçon Patel ») : 1 run/jour, caps RSS/tweets, solde
  prépayé bas, **backfill borné** (pas de boucle sur `advanced_search`, plafond
  strict ~1500 tweets).

> 🔧 **À confirmer / affiner :** ordres de grandeur réels constatés sur la facture
> Anthropic + twitterapi.io après quelques jours de run, si tu veux des chiffres
> précis plutôt que « quelques centimes/jour ».

## 7. Ce que ça illustre

- **Un agent utile tient en ~300 lignes et 0 serveur.** Collecte → résumé par
  l'API Claude → double publication, le tout orchestré par un cron GitHub
  Actions gratuit. Pas d'infra à gérer.
- **La bonne architecture évite les galères.** Séparer moteur et affichage,
  isoler les secrets, figer un contrat de données (`feed.json`) : la plupart des
  bugs restants ont été des **détails d'intégration** (nom de secret, `if:`
  Actions, conflit de bridge), pas des trous de conception.
- **On garde l'humain (et le LLM) honnêtes.** Champs factuels relus depuis la
  source, jamais confiés au modèle ; copyright respecté (résumé FR, jamais de
  recopie) ; ligne éditoriale neutre et anti-hype, même quand l'info n'est pas
  flatteuse pour Anthropic.

> 🔧 **À confirmer / personnaliser :** brouillon de morale. Dis-moi l'angle à
> appuyer (autonomie non-dev, coût dérisoire, robustesse, neutralité éditoriale…)
> et je réécris.
