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
  # Enabled only once the site feed/contact have been validated and published.
  # Build in this throwaway checkout before committing: an invalid archive or
  # RSS stops publication; the previous public site remains untouched.
  if [ -f assets/podcast/feed.xml ] && [ -f scripts/build_podcast_feed.py ]; then
    # Images were rendered, tagged and validated BEFORE Telegram. Publish those
    # exact files; never re-render a second visual after sending the audio.
    python3 scripts/build_podcast_feed.py --archive-latest
    git add assets/podcast/episodes.json assets/podcast/feed.xml assets/podcast/archive/
    if [ -d assets/podcast/covers ]; then git add assets/podcast/covers/; fi
  fi
  git diff --cached --quiet && exit 0
  git commit --quiet -m 'data: podcasts IA, archives permanentes et flux'
  if git push --quiet origin HEAD:main; then exit 0; fi
  echo "Push concurrent, nouvel essai ($attempt/3)."
done
echo 'Échec de publication audio sur le site.' >&2
exit 1
