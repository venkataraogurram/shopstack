#!/usr/bin/env bash
# Shared helpers for the ShopStack scripts. Source, do not execute.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="$ROOT_DIR/terraform"

: "${AWS_REGION:=us-east-1}"
: "${PROJECT:=shopstack}"
: "${NAMESPACE:=shopstack}"
SERVICES=(catalog cart order)

# Prefer finch (macOS) and fall back to docker.
if command -v finch >/dev/null 2>&1; then
  CONTAINER_CLI=finch
else
  CONTAINER_CLI=docker
fi

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarn:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

require() {
  for bin in "$@"; do
    command -v "$bin" >/dev/null 2>&1 || die "missing required tool: $bin"
  done
}

tf_output() {
  terraform -chdir="$TF_DIR" output -raw "$1"
}

account_id() {
  aws sts get-caller-identity --query Account --output text
}

ecr_registry() {
  printf '%s.dkr.ecr.%s.amazonaws.com' "$(account_id)" "$AWS_REGION"
}

# Image tag = short git SHA (+ "-dirty" when the tree has uncommitted changes).
image_tag() {
  local sha
  sha="$(git -C "$ROOT_DIR" rev-parse --short=12 HEAD 2>/dev/null || echo "local")"
  if [ -n "$(git -C "$ROOT_DIR" status --porcelain 2>/dev/null)" ]; then
    sha="${sha}-dirty-$(date +%Y%m%d%H%M%S)"
  fi
  printf '%s' "$sha"
}
