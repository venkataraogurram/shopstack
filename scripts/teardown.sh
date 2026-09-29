#!/usr/bin/env bash
# Remove everything, in the right order:
#   1. the Ingress (so the controller deletes the ALB and its security groups),
#   2. the Helm release,
#   3. all Terraform-managed infrastructure.
# Deleting the cluster before the ALB would leave an orphaned load balancer.

source "$(dirname "$0")/lib.sh"
require aws kubectl helm terraform

read -r -p "This destroys the ShopStack cluster and all data. Type 'destroy' to continue: " answer
[ "$answer" = "destroy" ] || die "aborted"

if kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
  log "deleting ingress and waiting for the ALB to go away"
  kubectl -n "$NAMESPACE" delete ingress "$PROJECT" --ignore-not-found --timeout=300s
  kubectl delete ns "$NAMESPACE" --ignore-not-found --timeout=300s
fi

log "uninstalling AWS Load Balancer Controller"
helm -n kube-system uninstall aws-load-balancer-controller 2>/dev/null || true

log "terraform destroy"
terraform -chdir="$TF_DIR" destroy -auto-approve

log "teardown complete"
