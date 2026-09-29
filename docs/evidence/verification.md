# Verification record — live run, 2026-09-29, us-east-1

Outputs below were captured from the deployed cluster. Raw files: `smoke-test.log`, `hpa-load-test.log`, `cluster-state.txt`.

## 1. End-to-end through the ALB (`scripts/smoke-test.sh`)

```
==> catalog                                   8 products
==> add two items to cart smoke-1790687868    subtotal_cents 3998 -> 10997
==> out-of-stock SKU is rejected              409
==> checkout                                  order 2069D51001C1 total_cents 10997 status CREATED
==> read order back / cart cleared            order=200 cart=404
==> smoke test passed
```

Order persisted in DynamoDB (`aws dynamodb get-item --table-name shopstack-orders --key '{"order_id":{"S":"777EC7113D45"}}'`):

```
| lines | order        | status  | total |
| 2     | 777EC7113D45 | CREATED | 10997 |
```

## 2. Pod Identity and least privilege

Environment injected by the EKS Pod Identity webhook into the `order` pod (no keys anywhere in the manifests):

```
AWS_CONTAINER_CREDENTIALS_FULL_URI=http://169.254.170.23/v1/credentials
AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE=/var/run/secrets/pods.eks.amazonaws.com/serviceaccount/eks-pod-identity-token
```

Run from inside a `cart` pod (`kubectl exec … python`):

```
identity:      arn:aws:sts::904233106520:assumed-role/shopstack-cart/eks-shopstack-cart-…
orders write:  AccessDeniedException        # cart role may not touch the orders table
carts describe: ACTIVE                      # its own table works
```

Associations on the cluster:

```
amazon-cloudwatch  cloudwatch-agent
kube-system        aws-load-balancer-controller
shopstack          cart
shopstack          order
```

## 3. Pod Security Standard (restricted) enforced

```
$ kubectl -n shopstack run pss-test --image=busybox --dry-run=server \
    --overrides='{"spec":{"containers":[{"name":"t","image":"busybox","securityContext":{"privileged":true}}]}}'
Error from server (Forbidden): pods "pss-test" is forbidden: violates PodSecurity "restricted:latest":
privileged (…), allowPrivilegeEscalation != false (…), unrestricted capabilities (…),
runAsNonRoot != true (…), seccompProfile (…)
```

## 4. Request tracing in CloudWatch Logs Insights

Query on `/aws/containerinsights/shopstack/application`:

```
fields @timestamp, kubernetes.container_name as svc, log
| filter kubernetes.namespace_name = "shopstack" and log like /smoke-1790686395/
| sort @timestamp asc
```

Result (10 rows, one checkout across three services):

```
catalog  GET    /catalog/products/TSH-001     200   1.09ms
cart     POST   /cart/smoke-…/items           200  60.81ms
catalog  GET    /catalog/products/SNK-003     200   0.92ms
cart     POST   /cart/smoke-…/items           200  27.95ms
cart     POST   /cart/smoke-…/items           409   5.86ms
cart     GET    /cart/smoke-…                 200   6.88ms
cart     DELETE /cart/smoke-…                 204   8.00ms
order    order created
order    POST   /orders                       201  85.23ms
cart     GET    /cart/smoke-…                 404   8.16ms
```

Container Insights: 414 metrics under `ContainerInsights` for `ClusterName=shopstack, Namespace=shopstack`. Log groups: `/aws/containerinsights/shopstack/{application,dataplane,host,performance}`.

## 5. Horizontal Pod Autoscaler (`scripts/load-test.sh <alb> 150 8`)

| time | catalog CPU (target 60%) | replicas |
|---|---|---|
| 18:48:12 | 2% | 2 |
| 18:48:32 | 248% | 2 |
| 18:48:51 | 441% | 6 |
| 18:49:11 → 18:50:50 | 245% → 167% | 6 |
| 18:51:10 | 82% (load ending) | 6 |

Zero `Pending` pods. Scale-down to 2 followed after the 120 s stabilization window.

First attempt (before prefix delegation) reached 5/6 with `0/2 nodes are available: 2 Too many pods` — t3.medium default ceiling is 17 pods/node. After enabling VPC CNI prefix delegation and `maxPods: 110`, the node group was replaced in place with no downtime (PDB `minAvailable: 1`, rolling `maxUnavailable: 0`) and the smoke test passed during the roll.
