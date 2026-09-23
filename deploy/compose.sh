#!/usr/bin/env bash
# `docker compose` pinned to the currently deployed image.
#   ./compose.sh ps
#   ./compose.sh logs -f api
#   ./compose.sh exec api python manage.py createsuperuser
set -euo pipefail
cd "$(dirname "$0")"

if [[ -z "${API_IMAGE:-}" ]]; then
  API_IMAGE="$(cat .current_image 2>/dev/null || true)"
fi
export API_IMAGE

exec docker compose "$@"
