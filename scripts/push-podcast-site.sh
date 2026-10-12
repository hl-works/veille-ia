#!/usr/bin/env bash
# Same daily pair as Telegram; never publish private previews or casting files.
set -euo pipefail
if [ -z "${KH_REPO_TOKEN:-}" ]; then
  echo 'KH_REPO_TOKEN absent : publication audio du site désactivée.'
  exit 0
fi
export GH_TOKEN="$KH_REPO_TOKEN"
ROOT="$(pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
# Authenticate without embedding the token in a remote URL.
gh auth setup-git
gh repo clone "${KH_REPO:-hl-works/knowledge-hub}" "$WORK/site" -- --depth 1 --branch main --quiet
cd "$WORK/site"
git config user.name veille-bot
git config user.email veille-bot@users.noreply.github.com
for attempt in 1 2 3; do
  git fetch --quiet origin main
  git reset --hard origin/main >/dev/null
  python3 "$ROOT/scripts/export-podcast.py" "$ROOT/audio-output" assets/podcast
  git add assets/podcast/short.mp3 assets/podcast/full.mp3 assets/podcast/latest.json 2>/dev/null || {
    echo 'Pas encore de duo public à exporter.'
    exit 0
  }
  git diff --cached --quiet && exit 0
  git commit --quiet -m 'data: derniers podcasts IA pour la home'
  if git push --quiet origin HEAD:main; then exit 0; fi
  echo "Push concurrent, nouvel essai ($attempt/3)."
done
echo 'Échec de publication audio sur le site.' >&2
exit 1
