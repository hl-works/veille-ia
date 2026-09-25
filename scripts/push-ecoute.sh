#!/usr/bin/env bash
# Publie le contenu de audio-output/ sur la branche `ecoute` du dépôt, dans le
# sous-dossier donné en argument. Branche d'écoute interne : rien n'est publié
# ailleurs (ni Telegram, ni site). Usage : push-ecoute.sh <dossier> [source]
set -euo pipefail
DEST="$1"
SRC="${2:-audio-output}"
[ -d "$SRC" ] && [ -n "$(ls -A "$SRC" 2>/dev/null)" ] || { echo "Rien à publier ($SRC vide)."; exit 0; }
URL="${ECOUTE_REMOTE:-https://x-access-token:${GH_TOKEN:-}@github.com/${GITHUB_REPOSITORY:-}.git}"
WORK="$(mktemp -d)"
if ! git clone -q --depth 1 --branch ecoute "$URL" "$WORK" 2>/dev/null; then
  git -C "$WORK" init -q -b ecoute
  git -C "$WORK" remote add origin "$URL"
  printf "# Écoute\n\nPodcasts et castings de voix à valider par Hugo. Rien ici n'est publié.\n" > "$WORK/README.md"
fi
mkdir -p "$WORK/$DEST"
cp -r "$SRC"/. "$WORK/$DEST/"
cd "$WORK"
git config user.name "veille-bot"
git config user.email "veille-bot@users.noreply.github.com"
git add -A
git commit -qm "écoute: $DEST" || { echo "Rien de nouveau."; exit 0; }
for i in 1 2 3; do
  git push -q origin ecoute && { echo "✓ Publié sur la branche ecoute : $DEST"; exit 0; }
  git pull -q --rebase origin ecoute || true
done
echo "Échec du push vers ecoute" >&2; exit 1
