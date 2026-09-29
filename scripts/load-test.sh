#!/usr/bin/env bash
# Generate CPU load on the catalog service so the HPA scales it out, and print
# the HPA/pod state every 15 seconds while it does.
#
#   scripts/load-test.sh http://<alb-hostname> [duration-seconds] [concurrency]
#
# Uses an in-cluster load generator so the traffic hits the Service directly
# (and is not throttled by your laptop's uplink).

source "$(dirname "$0")/lib.sh"
require kubectl

BASE="${1:-}"; DURATION="${2:-180}"; CONCURRENCY="${3:-8}"
[ -n "$BASE" ] || die "usage: $0 http://<alb-hostname> [duration] [concurrency]"

log "starting $CONCURRENCY in-cluster load generators for ${DURATION}s against catalog"
for i in $(seq 1 "$CONCURRENCY"); do
  kubectl -n "$NAMESPACE" run "loadgen-$i" --restart=Never --image=public.ecr.aws/docker/library/busybox:1.36 \
    --labels=app.kubernetes.io/name=loadgen --overrides='{
      "spec": {
        "securityContext": {"runAsNonRoot": true, "runAsUser": 10001, "seccompProfile": {"type": "RuntimeDefault"}},
        "containers": [{
          "name": "loadgen", "image": "public.ecr.aws/docker/library/busybox:1.36",
          "command": ["sh", "-c", "end=$(( $(date +%s) + '"$DURATION"' )); while [ $(date +%s) -lt $end ]; do wget -q -O /dev/null http://catalog/catalog/products; done"],
          "resources": {"requests": {"cpu": "50m", "memory": "32Mi"}, "limits": {"memory": "64Mi"}},
          "securityContext": {"allowPrivilegeEscalation": false, "capabilities": {"drop": ["ALL"]}}
        }]
      }
    }' >/dev/null
done

END=$(( $(date +%s) + DURATION + 30 ))
while [ "$(date +%s)" -lt "$END" ]; do
  echo "--- $(date +%H:%M:%S)"
  kubectl -n "$NAMESPACE" get hpa catalog --no-headers
  kubectl -n "$NAMESPACE" get pods -l app.kubernetes.io/name=catalog --no-headers | awk '{print "  " $1, $3}'
  sleep 15
done

log "cleaning up load generators"
kubectl -n "$NAMESPACE" delete pod -l app.kubernetes.io/name=loadgen --ignore-not-found >/dev/null
log "done; the HPA scales back down after its 120s stabilization window"
