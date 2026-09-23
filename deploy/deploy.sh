#!/usr/bin/env bash
# Deploy one API image:  ./deploy.sh ghcr.io/<owner>/sajilokabadi-api:develop-<sha>
#
# Order is chosen so the running API keeps serving until the new one is ready:
#   1. pull the new image          (old container still serving)
#   2. run migrations in a one-off container from the new image
#                                  (old container still serving; if this
#                                   fails, nothing has been switched)
#   3. replace the API container and wait for its healthcheck
#                                  (a few seconds of downtime)
#   4. if it never gets healthy, put the previous image back and fail
#
# Set SKIP_MIGRATIONS=1 to skip step 2 (used by rollback.sh).
# Never touches the postgres_data volume.
set -euo pipefail
cd "$(dirname "$0")"

NEW_IMAGE="${1:?usage: ./deploy.sh <image:tag>}"
CURRENT_IMAGE="$(cat .current_image 2>/dev/null || true)"
KEEP_IMAGES=3

log() { echo "[deploy $(date -u +%H:%M:%S)] $*"; }

log "Deploying $NEW_IMAGE (current: ${CURRENT_IMAGE:-none})"
mkdir -p media

log "Pulling image"
docker pull --quiet "$NEW_IMAGE"

export API_IMAGE="$NEW_IMAGE"

log "Making sure PostgreSQL is up"
docker compose up -d --wait postgres

if [[ "${SKIP_MIGRATIONS:-0}" != "1" ]]; then
  log "Running migrations with the new image"
  docker compose run --rm --no-deps api python manage.py migrate --noinput
fi

log "Switching the API container"
if ! docker compose up -d --no-deps --wait --wait-timeout 120 api; then
  log "New API container did not become healthy. Last logs:"
  docker compose logs --tail 80 api || true
  if [[ -n "$CURRENT_IMAGE" && "$CURRENT_IMAGE" != "$NEW_IMAGE" ]]; then
    log "Restoring previous image $CURRENT_IMAGE"
    API_IMAGE="$CURRENT_IMAGE" docker compose up -d --no-deps --wait --wait-timeout 120 api || true
  fi
  exit 1
fi

log "Checking /health/ locally"
curl -fsS --retry 5 --retry-delay 2 --retry-all-errors http://127.0.0.1:8000/health/
echo

if [[ -n "$CURRENT_IMAGE" && "$CURRENT_IMAGE" != "$NEW_IMAGE" ]]; then
  echo "$CURRENT_IMAGE" > .previous_image
fi
echo "$NEW_IMAGE" > .current_image
echo "$(date -u +%FT%TZ) $NEW_IMAGE" >> deploy-history.log

log "Removing old images (keeping the newest $KEEP_IMAGES of this repo)"
REPO="${NEW_IMAGE%:*}"
PREVIOUS_IMAGE="$(cat .previous_image 2>/dev/null || true)"
docker images "$REPO" --format '{{.Repository}}:{{.Tag}}' \
  | { grep -v ':<none>$' || true; } \
  | tail -n +$((KEEP_IMAGES + 1)) \
  | while read -r image; do
      if [[ "$image" != "$NEW_IMAGE" && "$image" != "$PREVIOUS_IMAGE" && "$image" != "$REPO:develop" ]]; then
        docker rmi "$image" >/dev/null 2>&1 && log "Removed $image" || true
      fi
    done
docker image prune -f >/dev/null

log "Done: $NEW_IMAGE is live"
