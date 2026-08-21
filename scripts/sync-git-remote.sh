#!/usr/bin/env bash
# Point origin at the renamed GitHub repository (VoxFauge → VoxForge).
set -euo pipefail

TARGET="https://github.com/Brohammad/VoxForge.git"
CURRENT="$(git remote get-url origin 2>/dev/null || true)"

if [[ "$CURRENT" == "$TARGET" ]]; then
  echo "origin already set to $TARGET"
  exit 0
fi

echo "Updating origin: ${CURRENT:-<unset>} -> $TARGET"
git remote set-url origin "$TARGET"
git remote -v
