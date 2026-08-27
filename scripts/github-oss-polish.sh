#!/usr/bin/env bash
# Set GitHub repo topics and file good-first issues for OSS contributors.
#
# Usage:
#   ./scripts/github-oss-polish.sh
#
# Requires: gh CLI authenticated for Brohammad/VoxForge
set -euo pipefail

REPO="${GITHUB_REPOSITORY:-Brohammad/VoxForge}"

echo "==> Setting repository topics on ${REPO}"
gh repo edit "$REPO" \
  --description "Open-source voice AI infrastructure — unified pipeline, RAG, evaluation, replay, handoff. Live: voxforge.brohammad.tech" \
  --homepage "https://voxforge.brohammad.tech" \
  --add-topic voice-ai \
  --add-topic fastapi \
  --add-topic langgraph \
  --add-topic livekit \
  --add-topic docker \
  --add-topic python \
  --add-topic open-source \
  --add-topic rag \
  --add-topic mcp \
  --add-topic postgres

ensure_label() {
  local name="$1"
  local color="$2"
  local desc="$3"
  if ! gh label list --repo "$REPO" --json name --jq '.[].name' | grep -qx "$name"; then
    gh label create "$name" --repo "$REPO" --color "$color" --description "$desc" || true
  fi
}

ensure_label "good first issue" "7057ff" "Good for newcomers"
ensure_label "documentation" "0075ca" "Improvements or additions to documentation"
ensure_label "enhancement" "a2eeef" "New feature or request"

create_issue_if_missing() {
  local title="$1"
  local body="$2"
  if gh issue list --repo "$REPO" --state all --search "$title in:title" --json title --jq '.[].title' | grep -qx "$title"; then
    echo "SKIP (exists): $title"
    return
  fi
  gh issue create --repo "$REPO" --title "$title" --label "good first issue,documentation" --body "$body"
}

echo "==> Creating good first issues"
create_issue_if_missing \
  "Add .docx parser for knowledge uploads" \
  "## Context
Dashboard and API accept PDF/TXT today; \`.docx\` was removed from file pickers until a parser exists.

## Scope
- Add \`.docx\` extraction (e.g. python-docx or unstructured)
- Wire into knowledge ingestion pipeline
- Unit test with a tiny fixture file
- Re-enable \`.docx\` in dashboard upload picker

## References
- \`src/voxforge/modules/knowledge/\`
- PM tasklist non-goal predecessor in Stage 1"

create_issue_if_missing \
  "Record 60s demo showcase video for README" \
  "## Context
README has an animated GIF; launch checklist also calls for a short MP4 showcase.

## Scope
- Record 60s of \`/demo\` + dashboard on production or local with real providers
- Export to \`docs/assets/demo-showcase-60s.mp4\`
- Link from README and \`docs/demo/recording-checklist.md\`

## References
- \`docs/demo/recording-checklist.md\`
- \`scripts/prove-real-voice.sh\`"

create_issue_if_missing \
  "Improve mobile layout for dashboard hub navigation" \
  "## Context
Dashboard IA uses Talk / Knowledge / Inbox / Settings hubs. Sidebar may overflow on narrow viewports.

## Scope
- CSS-only responsive pass for \`dashboard/static/styles.css\`
- Collapsible sidebar or top nav under ~768px
- Playwright smoke optional (viewport 375px)

## References
- \`dashboard/index.html\`, \`dashboard/static/app.js\`"

create_issue_if_missing \
  "Enable GitHub Discussions with pilot Q&A category" \
  "## Context
Launch checklist item: enable Discussions for community/pilot questions.

## Scope
- Enable Discussions on the repo (maintainer action)
- Add \`.github/DISCUSSION_TEMPLATE/\` or pinned welcome post
- Link from README Contributing section

## References
- \`docs/launch/LAUNCH-CHECKLIST.md\`"

echo "==> Done. Review issues: https://github.com/${REPO}/issues"
