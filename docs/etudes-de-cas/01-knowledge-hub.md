# Étude de cas — Knowledge Hub : de l'idée à la prod

> **Build in public.** Un non-développeur livre et fait vivre un site complet
> avec Claude Code. Récit honnête, ordres de grandeur assumés, zéro chiffre inventé.

> ⚠️ **Cadre honnête.** Ce récit ne couvre pas la création *ex nihilo* du site.
> Le socle existait déjà (43 entrées de journal, 4 verticales, recherche, coffre
> chiffré, design system « HiFi Lovers ») — bâti dans une session antérieure.
> Cette étude de cas porte sur la **couche éditoriale + UX** ajoutée par-dessus :
> guides evergreen, lexique, dark mode, refonte nav, couche GEO.

---

## 1. Le déclic / le besoin de départ

Le site avait déjà un journal riche — 43 entrées — mais **peu de contenu
evergreen**. Or un journal, ça vit dans l'instant et ça date vite. Il me
manquait du contenu qui **fait autorité dans la durée** : lisible par un humain
pressé, et **citable par les LLM** (le fameux GEO, *Generative Engine
Optimization* — être référencé par les IA quand elles répondent).

Deux moteurs derrière, assumés :

- **Centraliser mes notes IA** dans un endroit unique, propre, qui ne se perd pas
  dans des favoris et des captures d'écran.
- **Avoir une vitrine publique** à mon nom, partageable — et au passage,
  **prouver qu'un non-développeur peut livrer et faire vivre un site complet
  avec Claude Code**.

Cible affichée : **marchands / dirigeants** qui captent vite, sans exclure les
débutants.

## 2. L'idée → le cadrage (décisions, alternatives écartées)

Le choix de stack a été tranché tôt, et en partie **sur conseil de l'IA** quand
j'ai décrit le besoin. Trois principes non négociables :

- **Simplicité / zéro build.** Pas de toolchain, pas de `npm`, pas d'étape de
  compilation à maintenir. J'ouvre un `.html`, ça marche. C'est ce qui me garde
  autonome.
- **Gratuit + hébergement simple.** GitHub Pages : pas de serveur, déploiement
  au push (~1 min). *Écarté :* Vercel/Netlify (superflus ici), un VPS (trop
  lourd).
- **Pas de framework.** *Écarté :* React / Next / Astro / un générateur statique
  — overkill pour le besoin et une dette de maintenance pour un non-dev.

Décisions structurantes de cette session :

| Décision | Pourquoi | Alternative écartée |
|---|---|---|
| **Guides evergreen** : 1 page = 1 grande question, 3 niveaux (« En 30 s » → corps visuel → « Pour aller plus loin ») | Une URL qui fait autorité par question (bon pour le SEO) | Pages séparées débutant/avancé (dilue l'autorité) |
| **Visuels codés** en HTML/CSS/SVG inline | Zéro image lourde, zéro dépendance | Librairies de graphes |
| **Logos acteurs recodés en SVG inline** | Robustesse, légèreté | Fichiers logos officiels |
| **Cluster sur la landing** (Comprendre / Outiller / Méthode / Décider) | Autorité thématique, moins de dilution | Multiplier les sections de nav |
| **Dark mode par tokens CSS** (`[data-theme]`) + toggle Auto/Clair/Sombre, fond anthracite chaud | Garder l'ADN visuel | Gris neutre froid / noir pur |
| **Header allégé / footer enrichi** | Lexique & réseaux descendent en footer | — |
| **Anti-FOUC** : script inline dans le `<head>` (~3 lignes, seul JS bloquant toléré) | Éviter le flash de thème au chargement | — |
| **Faits vérifiés, jamais de versions de modèles** | Rester evergreen | Citer des numéros de version qui périment |

> Exemples de faits vérifiés et figés : Karpathy → Anthropic (mai 2026),
> *Compound Engineering* attribué à Klaassen & Shipper / Every, « AI is the new
> electricity » = Andrew Ng.

## 3. Le « vibe coding » : comment ça s'est construit, étape par étape

Outil principal : **Claude Code**, en **terminal** et **sur le web/app**, qui
écrit, modifie et committe directement dans le repo. Ma boucle de travail :
**aperçu visuel dans le navigateur → je redemande des ajustements → re-rendu**,
en boucle, jusqu'à ce que ça me plaise.

Le déroulé réel de la session :

1. **Lecture du repo + cadrage des conventions** (gabarits, tags, cache-busting).
2. **Lancement de `/guides/`** avec le Guide #1 (IA/LLM) et ses 3 visuels codés.
3. **Production par batchs** : guides #2→#4, puis #5→#11, puis #12, puis
   #13→#15 (orientés SEO/GEO).
4. **Clustering de la landing** en 4 familles.
5. **Micro-optimisations SEO** (entité auteur `@id`, `HowTo`).
6. **Refonte header/footer** (réseaux, contact LinkedIn + mail,
   `SiteNavigationElement`).
7. **Dark mode** : démo sur l'accueil → validation → propagation sur 72 pages →
   finitions.
8. **Lexique** : ajout des 9 grands acteurs IA.

## 4. La stack + les outils

- **[Claude Code](https://claude.com/claude-code)** — l'agent de construction
  (rédaction + code + commits).
- **HTML / CSS / JS vanilla** — zéro framework, un seul `style.css` (~750 lignes).
- **[GitHub](https://github.com)** — versionnage + source de vérité.
- **[GitHub Pages](https://pages.github.com)** — hébergement + déploiement auto à
  chaque push (~1 min). Fichier `.nojekyll` pour servir le statique tel quel.
- **[schema.org](https://schema.org) JSON-LD** (`TechArticle`, `FAQPage`,
  `HowTo`, `BreadcrumbList`, `SiteNavigationElement`, `Person`) +
  **`llms.txt` / `llms-full.txt`** — la couche **GEO**.

> Pas d'API ni de planificateur pour ce projet : **tout passe par mon abonnement
> Claude** — donc pas de tokens facturés à l'usage.

## 5. Les galères (ce qui a cassé et comment on a réglé)

- **Le flash de thème (FOUC).** Au chargement, la page clignotait en clair avant
  de passer en sombre. → Réglé par un **script inline de ~3 lignes dans le
  `<head>`**, le seul JS bloquant que je tolère, qui applique le thème avant le
  premier rendu.
- **Le cache iOS têtu.** Safari/iOS gardait l'ancien CSS/JS. → **Cache-busting
  discipliné** (`?v=…`) à chaque modif d'asset pour forcer le rechargement.
- **Deux sessions en parallèle sur `main`.** Je bossais sur plusieurs sessions
  qui poussaient sur la même branche → risque de collision. → Garde-fou :
  **resync systématique (`fetch` + ff/rebase) avant chaque push**, et **scripts
  idempotents** (rejouables sans rien casser).
- **Ne jamais toucher au coffre.** Règle dure : `coffre.js` / `vault.json` (AES)
  sont intouchables. Le dark mode a été **volontairement non appliqué au
  coffre** pour ne pas risquer de le casser. Respecté.

## 6. Temps passé (réel) et tokens / coût

- **3 jours calendaires** : 30 mai → 1ᵉʳ juin 2026.
- **~70 commits** sur la période (dont une bonne partie pour cette session :
  guides, lexique, dark mode, nav/footer).
- Découpé en **plusieurs sessions courtes** dans la journée (matin / après-midi /
  soir, d'après l'horodatage Git).
- **Coût : aucun au token** — tout passe par l'abonnement Claude, pas d'API.
  Pour ce cas, on parle **temps**, pas coût.

> 🔧 **À confirmer par Hugo :** la **durée active réelle** (« temps assis »).
> Git donne les jalons (3 jours, ~70 commits), pas le temps réellement passé
> devant l'écran. Donne-moi le chiffre que tu assumes et je remplace cette note.

## 7. Ce que ça illustre

- **Pas besoin de framework pour livrer.** Du HTML/CSS/JS vanilla + GitHub Pages
  suffisent à tenir un site de 70+ pages, propre, rapide, avec dark mode et une
  couche GEO sérieuse.
- **L'IA déplace le goulot d'étranglement.** Le travail n'est plus « savoir
  coder », c'est **décider** (architecture, conventions, ton éditorial) et
  **vérifier** (faits, rendu, garde-fous). Claude Code fait la frappe ; moi je
  fais les choix.
- **L'honnêteté est une feature.** Assumer un socle préexistant, des ordres de
  grandeur plutôt que de faux chiffres, des claims prudents sur les sujets
  sensibles (GEO = champ émergent) → ça rend le tout crédible et citable.

> 🔧 **À confirmer / personnaliser :** la morale ci-dessus est un brouillon.
> Dis-moi si tu veux insister sur un angle (autonomie du non-dev, GEO, vitesse,
> coût nul…) et je réécris.
