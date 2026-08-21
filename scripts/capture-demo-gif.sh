#!/usr/bin/env bash
# Build docs/assets/screenshots/demo.gif from a screen recording of /demo.
#
# Record 10–15s showing:
#   1. Provider badge (mock/live)
#   2. Click "Run one-click sample call"
#   3. Chat reply + in-browser TTS playback
#
# Usage:
#   ./scripts/capture-demo-gif.sh path/to/recording.mp4
#
# Requires: ffmpeg
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INPUT="${1:?Usage: $0 path/to/recording.mp4}"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ERROR: ffmpeg is required" >&2
  exit 1
fi

DOCS_GIF="${ROOT}/docs/assets/screenshots/demo.gif"
PUBLIC_GIF="${ROOT}/public/assets/screenshots/demo.gif"
mkdir -p "$(dirname "$DOCS_GIF")" "$(dirname "$PUBLIC_GIF")"

ffmpeg -y -i "$INPUT" \
  -vf "fps=8,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer" \
  -loop 0 "$DOCS_GIF"

cp "$DOCS_GIF" "$PUBLIC_GIF"

BYTES="$(wc -c < "$DOCS_GIF" | tr -d ' ')"
echo "Wrote ${DOCS_GIF} (${BYTES} bytes)"
echo "Copied to ${PUBLIC_GIF}"
if [[ "$BYTES" -gt 5242880 ]]; then
  echo "WARN: GIF is >5MB — consider a shorter clip or lower fps in this script." >&2
fi
