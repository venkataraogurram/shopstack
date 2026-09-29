#!/usr/bin/env bash
# Configure kubectl for the cluster and install the AWS Load Balancer Controller
# with Helm. metrics-server (for HPA) and the CloudWatch Observability agent are
# installed as EKS managed add-ons by Terraform, so nothing else is needed here.
#
# Idempotent: safe to re-run.

source "$(dirname "$0")/lib.sh"
require aws kubectl helm terraform

CLUSTER="$(tf_output cluster_name)"
VPC_ID="$(tf_output vpc_id)"

log "updating kubeconfig for $CLUSTER"
aws eks update-kubeconfig --region "$AWS_REGION" --name "$CLUSTER" >/dev/null

log "waiting for nodes to be Ready"
kubectl wait --for=condition=Ready nodes --all --timeout=300s

log "installing AWS Load Balancer Controller"
helm repo add eks https://aws.github.io/eks-charts >/dev/null 2>&1 || true
helm repo update eks >/dev/null

# The ServiceAccount is created by the chart; its IAM role is attached by the
# Pod Identity association Terraform created for kube-system/aws-load-balancer-controller.
helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
  --namespace kube-system \
  --set clusterName="$CLUSTER" \
  --set region="$AWS_REGION" \
  --set vpcId="$VPC_ID" \
  --set serviceAccount.create=true \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set replicaCount=2 \
  --set resources.requests.cpu=100m \
  --set resources.requests.memory=128Mi \
  --wait --timeout 5m

log "waiting for metrics-server (EKS add-on)"
kubectl -n kube-system rollout status deployment/metrics-server --timeout=180s

log "add-on status"
kubectl -n kube-system get deploy aws-load-balancer-controller metrics-server
kubectl -n amazon-cloudwatch get daemonset 2>/dev/null || warn "CloudWatch observability add-on not ready yet"
