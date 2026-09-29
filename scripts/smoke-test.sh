#!/usr/bin/env bash
# End-to-end check through the public ALB: browse -> add to cart -> checkout -> read order.
#
#   scripts/smoke-test.sh http://<alb-hostname>

source "$(dirname "$0")/lib.sh"
require curl python3

BASE="${1:-}"
[ -n "$BASE" ] || die "usage: $0 http://<alb-hostname>"
BASE="${BASE%/}"
CART="smoke-$(date +%s)"
RID="smoke-$(date +%s)"

json() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)"; }

log "catalog"
COUNT=$(curl -fsS "$BASE/catalog/products" | json "len(d)")
echo "  $COUNT products"

log "add two items to cart $CART"
curl -fsS -X POST "$BASE/cart/$CART/items" -H 'content-type: application/json' -H "X-Request-ID: $RID" \
  -d '{"sku":"TSH-001","qty":2}' | json "'  subtotal_cents', d['subtotal_cents']"
curl -fsS -X POST "$BASE/cart/$CART/items" -H 'content-type: application/json' -H "X-Request-ID: $RID" \
  -d '{"sku":"SNK-003","qty":1}' | json "'  subtotal_cents', d['subtotal_cents']"

log "out-of-stock SKU is rejected (expect 409)"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/cart/$CART/items" \
  -H 'content-type: application/json' -d '{"sku":"BLT-007","qty":1}')
echo "  $code"; [ "$code" = "409" ] || die "expected 409, got $code"

log "checkout"
ORDER=$(curl -fsS -X POST "$BASE/orders" -H 'content-type: application/json' -H "X-Request-ID: $RID" \
  -d "{\"cart_id\":\"$CART\",\"customer_email\":\"smoke@example.com\"}")
OID=$(echo "$ORDER" | json "d['order_id']")
echo "$ORDER" | json "'  order', d['order_id'], 'total_cents', d['total_cents'], 'status', d['status']"

log "read order back (expect 200) and confirm cart was cleared (expect 404)"
o=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/orders/$OID")
c=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/cart/$CART")
echo "  order=$o cart=$c"
[ "$o" = "200" ] && [ "$c" = "404" ] || die "unexpected status codes"

log "smoke test passed (request id $RID)"
