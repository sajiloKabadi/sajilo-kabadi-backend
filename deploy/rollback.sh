#!/usr/bin/env bash
# Put a previous API image back.
#   ./rollback.sh                       -> the image deployed before the current one
#   ./rollback.sh develop-a1b2c3d       -> a specific commit's image
#   ./rollback.sh ghcr.io/o/r:tag       -> a full image reference
#
# Migrations are NOT reversed. Code rollbacks are safe as long as the newer
# migrations only added things (new tables, nullable columns); see
# docs/deploy/DEV_DEPLOYMENT.md, "Rollback".
set -euo pipefail
cd "$(dirname "$0")"

CURRENT_IMAGE="$(cat .current_image 2>/dev/null || true)"
TARGET="${1:-$(cat .previous_image 2>/dev/null || true)}"

if [[ -z "$TARGET" ]]; then
  echo "No previous image recorded. Pass a tag, e.g. ./rollback.sh develop-a1b2c3d" >&2
  echo "Recent deploys:" >&2
  tail -n 10 deploy-history.log 2>/dev/null >&2 || true
  exit 1
fi

# A bare tag means "same repository as the current image".
if [[ "$TARGET" != *"/"* ]]; then
  TARGET="${CURRENT_IMAGE%:*}:$TARGET"
fi

echo "Rolling back: $CURRENT_IMAGE -> $TARGET"
SKIP_MIGRATIONS=1 ./deploy.sh "$TARGET"
