#!/usr/bin/env bash
# Deploy (or roll out a new image tag of) the ShopStack services.
#
#   scripts/deploy.sh <image-tag>
#
# Builds a throw-away Kustomize overlay on top of k8s/ that pins every image to
# the given tag, applies it, and waits for all rollouts to finish.

source "$(dirname "$0")/lib.sh"
require aws kubectl terraform

TAG="${1:-}"
[ -n "$TAG" ] || die "usage: $0 <image-tag>   (tag printed by scripts/build-push.sh)"

REGISTRY="$(ecr_registry)"
OVERLAY="$ROOT_DIR/.deploy"
mkdir -p "$OVERLAY"

{
  echo "apiVersion: kustomize.config.k8s.io/v1beta1"
  echo "kind: Kustomization"
  echo "resources:"
  echo "  - ../k8s"
  echo "images:"
  for svc in "${SERVICES[@]}"; do
    echo "  - name: ${PROJECT}/${svc}"
    echo "    newName: ${REGISTRY}/${PROJECT}/${svc}"
    echo "    newTag: \"${TAG}\""
  done
} > "$OVERLAY/kustomization.yaml"

log "applying manifests with image tag $TAG"
kubectl apply -k "$OVERLAY"

for svc in "${SERVICES[@]}"; do
  log "waiting for rollout: $svc"
  kubectl -n "$NAMESPACE" rollout status "deployment/$svc" --timeout=300s
done

log "waiting for the Application Load Balancer"
for _ in $(seq 1 40); do
  ALB="$(kubectl -n "$NAMESPACE" get ingress "$PROJECT" -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)"
  [ -n "$ALB" ] && break
  sleep 10
done
[ -n "${ALB:-}" ] || die "ingress did not receive an ALB hostname; check: kubectl -n kube-system logs deploy/aws-load-balancer-controller"

log "waiting for the ALB to answer"
for _ in $(seq 1 40); do
  if curl -fsS "http://$ALB/" >/dev/null 2>&1; then break; fi
  sleep 10
done

kubectl -n "$NAMESPACE" get deploy,hpa,ingress
log "ShopStack is live at http://$ALB"
echo "http://$ALB"
