# Making-of — Ce site (et un bot de veille IA) sortis en un week-end

> Bloc « coulisses » réutilisable : en page autonome, ou en encart en bas d'une
> page (études de cas, à-propos, landing).

## Le récit, version courte

**Vendredi 29 mai 2026, dîner entre amis.** Je reparle de ce que je bricole avec
l'IA. Comme j'avais déjà raconté la même chose au déjeuner, je me dis : il me
faut **un seul endroit** pour montrer tout ça, au lieu de le réexpliquer à
chaque fois.

**Samedi matin, je lance le site.** Et de fil en aiguille, tout s'enchaîne et
passe en prod presque aussitôt :

- un **journal**, un **lexique**, un système de **tags**, une **recherche** ;
- un **dark mode** propre (sur 72 pages) ;
- une page **Veille IA** ;
- et carrément **un bot** qui récupère l'actu IA, la fait résumer par l'API
  Claude, et la publie sur **Telegram** + sur le site.

Le tout pensé d'un bloc, jusqu'au **favicon / logo maison** (inspiré de Claude,
intégré à ma direction artistique) pour une **cohérence visuelle** complète.

**Un beau bébé sorti en ~2 jours** — sans être développeur, en binôme avec
**Claude Code**.

## Les deux cas d'usage à suivre

C'est ce que je documente en détail, chiffré en **temps** et en **coût** :

1. **[Le site Knowledge Hub](./01-knowledge-hub.md)** — site statique
   HTML/CSS/JS, zéro framework, sur GitHub Pages. *Coût au token : zéro*
   (abonnement Claude). On parle ici **temps**.
2. **[Le bot de veille IA](./02-veille-ia.md)** — un agent sans serveur (GitHub
   Actions) : X/Twitter → API Claude → Telegram + site. *Coût réel : quelques
   centimes/jour* (j'ai mis 100 € en prépayé « pour voir », ça dure très
   longtemps).

## Et après

Annonce **LinkedIn** du projet, **documentation du canal Telegram**, et suivi
public des deux chantiers dans la durée — parce que la meilleure preuve qu'un
non-dev peut livrer, c'est de **montrer le making-of, chiffres à l'appui**.
