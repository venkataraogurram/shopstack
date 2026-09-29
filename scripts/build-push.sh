#!/usr/bin/env bash
# Build all three service images for linux/amd64 and push them to ECR.
#
#   scripts/build-push.sh            # tag = git short SHA
#   TAG=v1.0.0 scripts/build-push.sh # explicit tag
#
# Prints the tag on the last line so callers can capture it:
#   TAG=$(scripts/build-push.sh | tail -1)

source "$(dirname "$0")/lib.sh"
require aws git "$CONTAINER_CLI"

TAG="${TAG:-$(image_tag)}"
REGISTRY="$(ecr_registry)"

log "logging in to $REGISTRY"
aws ecr get-login-password --region "$AWS_REGION" \
  | "$CONTAINER_CLI" login --username AWS --password-stdin "$REGISTRY" >/dev/null

for svc in "${SERVICES[@]}"; do
  IMAGE="${REGISTRY}/${PROJECT}/${svc}:${TAG}"
  log "building $IMAGE"
  "$CONTAINER_CLI" build --platform linux/amd64 \
    --build-arg "APP_VERSION=${TAG}" \
    -t "$IMAGE" "$ROOT_DIR/services/$svc" >/dev/null
  log "pushing $IMAGE"
  "$CONTAINER_CLI" push --platform linux/amd64 "$IMAGE" >/dev/null
done

log "pushed tag $TAG for: ${SERVICES[*]}"
echo "$TAG"
