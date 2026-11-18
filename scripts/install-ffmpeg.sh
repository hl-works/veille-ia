#!/usr/bin/env bash
# Installe ffmpeg vite et sans jamais bloquer le job (incident du 18/11/2026 :
# « apt-get update » a pris 21 min sur le runner et fait sauter le podcast).
set -uo pipefail
if command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null; then
  echo "ffmpeg déjà présent."; exit 0
fi
# 1) apt sans mise à jour des listes (rapide si les listes de l'image suffisent)
if timeout 180 sudo apt-get install -y -qq --no-install-recommends ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg installé (apt)."; exit 0
fi
# 2) binaire statique (GitHub, rapide et fiable)
url="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
dir="$HOME/.ffmpeg-static"
mkdir -p "$dir"
if timeout 180 curl -fsSL "$url" | tar -xJ -C "$dir" --strip-components=1; then
  echo "$dir/bin" >> "${GITHUB_PATH:-/dev/null}"
  export PATH="$dir/bin:$PATH"
  echo "ffmpeg installé (binaire statique)."; exit 0
fi
# 3) dernier recours : apt complet, borné
timeout 360 sudo apt-get update -qq && timeout 240 sudo apt-get install -y -qq --no-install-recommends ffmpeg \
  && { echo "ffmpeg installé (apt complet)."; exit 0; }
echo "Impossible d'installer ffmpeg." >&2; exit 1
