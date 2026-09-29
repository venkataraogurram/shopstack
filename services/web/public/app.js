/* ShopStack storefront. Talks to the catalog, cart and order services through
 * the same origin; the ALB routes /catalog, /cart and /orders to the backends. */

const $ = (sel) => document.querySelector(sel);
const money = (cents, cur = "USD") =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: cur }).format(cents / 100);
// crypto.randomUUID() exists only in secure contexts (HTTPS/localhost); the
// demo runs on the plain-HTTP ALB hostname, so build ids from getRandomValues.
const randomId = (len) =>
  Array.from(crypto.getRandomValues(new Uint8Array(len)), (b) => b.toString(16).padStart(2, "0")).join("").slice(0, len);
const colors = ["#1f6feb", "#8250df", "#bf3989", "#cf222e", "#bc4c00", "#4d2d00", "#1a7f37", "#0969da"];

// One anonymous cart per browser
const cartId = localStorage.getItem("shopstack.cart") || randomId(12);
localStorage.setItem("shopstack.cart", cartId);

let products = [];
let cart = null;

/* ---------- HTTP ---------- */
async function api(method, path, body) {
  const rid = randomId(16);
  const res = await fetch(path, {
    method,
    headers: { "content-type": "application/json", "x-request-id": rid },
    body: body ? JSON.stringify(body) : undefined,
  });
  $("#last-call").textContent = `${method} ${path} → ${res.status} (request id ${rid})`;
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.detail || res.statusText), { status: res.status, data });
  return data;
}

function toast(msg, isErr = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (isErr ? " err" : "");
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 2800);
}

/* ---------- Catalog ---------- */
async function loadCatalog() {
  try {
    products = await api("GET", "/catalog/products");
  } catch (e) {
    $("#products").innerHTML = `<p class="muted">Catalog unavailable (${e.message}).</p>`;
    return;
  }
  $("#products").innerHTML = products
    .map((p, i) => {
      const initials = p.name.split(" ").slice(0, 2).map((w) => w[0]).join("");
      return `
      <article class="card">
        <div class="thumb" style="background:${colors[i % colors.length]}">${initials}</div>
        <h3>${p.name}</h3>
        <p>${p.description}</p>
        <div class="price-row">
          <span class="price">${money(p.unit_price_cents, p.currency)}</span>
          ${p.in_stock
            ? `<button class="add" data-sku="${p.sku}">Add to cart</button>`
            : `<span class="chip">Out of stock</span>`}
        </div>
      </article>`;
    })
    .join("");
}

/* ---------- Cart ---------- */
async function refreshCart() {
  try {
    cart = await api("GET", `/cart/${cartId}`);
  } catch (e) {
    if (e.status !== 404) toast(`Cart error: ${e.message}`, true);
    cart = null;
  }
  renderCart();
}

function renderCart() {
  const items = cart?.items ?? [];
  const count = items.reduce((n, i) => n + i.qty, 0);
  $("#cart-count").textContent = count;
  $("#cart-subtotal").textContent = money(cart?.subtotal_cents ?? 0);
  $("#btn-checkout").disabled = items.length === 0;
  $("#cart-items").innerHTML = items.length
    ? items
        .map(
          (i) => `
        <div class="line">
          <span class="name">${i.name}</span>
          <span class="sub">${i.sku} · ${money(i.unit_price_cents)} each</span>
          <span class="qty">
            <button data-qty="${i.sku}:${i.qty - 1}" aria-label="Decrease">−</button>
            <span>${i.qty}</span>
            <button data-qty="${i.sku}:${i.qty + 1}" aria-label="Increase">+</button>
            <button class="remove" data-remove="${i.sku}">remove</button>
          </span>
          <span class="total">${money(i.line_total_cents)}</span>
        </div>`
        )
        .join("")
    : `<p class="muted">Your cart is empty. Add something from the catalog.</p>`;
}

async function setQty(sku, qty) {
  try {
    if (qty <= 0) {
      cart = await api("DELETE", `/cart/${cartId}/items/${sku}`);
    } else {
      cart = await api("POST", `/cart/${cartId}/items`, { sku, qty });
    }
    renderCart();
  } catch (e) {
    toast(e.message, true);
  }
}

/* ---------- Orders ---------- */
function renderOrder(o) {
  $("#order-view").innerHTML = `
    <div class="order-ok">
      <h3>Order ${o.order_id}</h3>
      <dl class="kv">
        <dt>Status</dt><dd>${o.status}</dd>
        <dt>Email</dt><dd>${o.customer_email}</dd>
        <dt>Placed</dt><dd>${new Date(o.created_at * 1000).toLocaleString()}</dd>
        <dt>Total</dt><dd><strong>${money(o.total_cents, o.currency)}</strong></dd>
      </dl>
      ${o.items.map((i) => `<div class="row"><span>${i.qty} × ${i.name}</span><span>${money(i.line_total_cents)}</span></div>`).join("")}
    </div>`;
}

async function checkout(email) {
  const btn = $("#btn-checkout");
  btn.disabled = true;
  btn.textContent = "Placing order…";
  try {
    const order = await api("POST", "/orders", { cart_id: cartId, customer_email: email });
    closeDrawers();
    renderOrder(order);
    $("#lookup-id").value = order.order_id;
    openDrawer("#order-panel");
    toast(`Order ${order.order_id} placed`);
    await refreshCart();
  } catch (e) {
    toast(`Checkout failed: ${e.message}`, true);
    renderCart();
  } finally {
    btn.textContent = "Place order";
  }
}

async function lookupOrder(id) {
  try {
    renderOrder(await api("GET", `/orders/${id.trim()}`));
  } catch (e) {
    $("#order-view").innerHTML = `<p class="muted">${e.status === 404 ? "No order with that ID." : e.message}</p>`;
  }
}

/* ---------- Drawers ---------- */
function openDrawer(sel) {
  closeDrawers();
  $(sel).hidden = false;
  $("#backdrop").hidden = false;
}
function closeDrawers() {
  document.querySelectorAll(".drawer").forEach((d) => (d.hidden = true));
  $("#backdrop").hidden = true;
}

/* ---------- Wiring ---------- */
document.addEventListener("click", (ev) => {
  const t = ev.target.closest("button");
  if (!t) return;
  if (t.dataset.sku) {
    const current = cart?.items.find((i) => i.sku === t.dataset.sku)?.qty ?? 0;
    setQty(t.dataset.sku, current + 1).then(() => toast("Added to cart"));
  } else if (t.dataset.qty) {
    const [sku, qty] = t.dataset.qty.split(":");
    setQty(sku, Number(qty));
  } else if (t.dataset.remove) {
    setQty(t.dataset.remove, 0);
  } else if (t.hasAttribute("data-close")) {
    closeDrawers();
  }
});
$("#backdrop").addEventListener("click", closeDrawers);
$("#btn-cart").addEventListener("click", () => openDrawer("#cart-panel"));
$("#btn-orders").addEventListener("click", () => openDrawer("#order-panel"));
$("#checkout-form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  checkout($("#email").value);
});
$("#lookup-form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  lookupOrder($("#lookup-id").value);
});

// Which web pod served this page (Nginx sets X-Served-By)
fetch("/healthz", { cache: "no-store" })
  .then((r) => ($("#served-by").textContent = r.headers.get("x-served-by") || "unknown"))
  .catch(() => ($("#served-by").textContent = "unknown"));

loadCatalog();
refreshCart();
