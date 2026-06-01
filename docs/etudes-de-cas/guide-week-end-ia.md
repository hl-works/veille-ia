# Un non-développeur peut-il livrer un vrai site + un bot IA en un week-end ?

> **Gabarit guide evergreen** — 1 page = 1 grande question, 3 niveaux de lecture.
> À couler dans `/guides/` au format du site.

---

## En 30 secondes

**Oui.** En un week-end, sans savoir coder, j'ai mis en prod **deux choses
réelles** avec [Claude Code](https://claude.com/claude-code) :

- un **site statique** complet (journal, guides, lexique, recherche, dark mode,
  GEO) hébergé gratuitement sur GitHub Pages ;
- un **bot de veille IA** sans serveur qui résume l'actu et la publie chaque
  matin sur Telegram + sur le site.

Le secret n'est pas technique. C'est de **bien décider** (architecture simple,
zéro dépendance, contrat de données clair) et de **laisser l'IA frapper le
code**, pendant que vous vérifiez le rendu et les faits.

---

## Le corps du guide

### 1. Commencez par le besoin, pas par la techno

Mon déclencheur n'était pas « je veux faire un site ». C'était : *« j'en ai
marre de réexpliquer ce que je fais avec l'IA — il me faut un endroit unique. »*
Le besoin a dicté la forme.

### 2. Choisissez la stack la plus bête possible

- **Site** : HTML/CSS/JS **vanilla**, zéro framework, **zéro build**. On ouvre un
  `.html`, ça marche. Hébergement **GitHub Pages** (gratuit, déploiement au push).
- **Bot** : un script Python orchestré par **GitHub Actions** (un cron gratuit).
  Pas de serveur à gérer.

> Pourquoi si simple ? Parce qu'un non-dev doit pouvoir **maintenir** son projet
> seul. Chaque dépendance ajoutée est une dette future.

### 3. Séparez les responsabilités

Deux repos : le **bot = moteur de données**, le **site = affichage**. Reliés par
**un seul fichier** (`feed.json`). Bénéfice immédiat : les **secrets** (clés API,
token du bot) restent dans le repo privé du moteur — **le site public n'en
contient aucun**.

### 4. Travaillez en boucle visuelle avec l'IA

Mon rythme : **je décris → l'IA code et committe → je regarde le rendu dans le
navigateur → je redemande un ajustement.** En boucle. L'IA tient le clavier ;
moi je tiens les **choix** (ton, structure, garde-fous) et la **vérification**
(faits exacts, rien d'inventé).

### 5. Posez des garde-fous dès le départ

- **Budget** : 1 run/jour, plafonds stricts sur le volume collecté, pas de
  boucle qui s'emballe.
- **Copyright** : jamais de contenu recopié — toujours un **résumé reformulé** +
  le lien source.
- **Sécurité** : jamais de secret publié (placeholders partout), un jeton dédié
  par usage.

---

## Pour aller plus loin

- **[Étude de cas — le site Knowledge Hub](./01-knowledge-hub.md)** : décisions,
  galères (anti-FOUC, cache iOS), temps réel. *Coût au token : zéro* (abonnement).
- **[Étude de cas — le bot de veille IA](./02-veille-ia.md)** : architecture
  2 repos, bridge cross-repo, galères CI, **coût réel ~quelques centimes/jour**.
- **[Making-of](./03-making-of.md)** : le récit, du dîner entre amis au « beau
  bébé sorti en 2 jours ».

> **À retenir.** Le frein n'est plus *« je ne sais pas coder »*. Le travail qui
> reste — décider, cadrer, vérifier — est exactement celui qu'un dirigeant ou un
> marchand sait déjà faire.
