// Pi payment frontend snippet for BoTTube (SCAFFOLD, hardened after tri-brain review).
// Runs inside the Pi Browser. Pi is one payment option among RTC + fiat/USDC.
// Pair with pi_blueprint.py (/pi/approve, /pi/complete, /pi/health).
//
// Load the Pi SDK in the page <head>:  <script src="https://sdk.minepi.com/pi-sdk.js"></script>

let PI_CFG = { products: {} };

// Pull server-authoritative PRICES from /pi/health. NOTE: Pi.init's `sandbox` is the
// desktop Pi Sandbox flag and MUST be false inside the real Pi Browser (same as
// pi_auth.js) — it is NOT the testnet/mainnet switch (that is the server's PI_SANDBOX,
// surfaced as /pi/health.sandbox for the API base, and must not drive Pi.init here).
async function piInit() {
  try {
    const cfg = await (await fetch("/pi/health")).json();
    PI_CFG.products = cfg.products || {};   // server-authoritative prices
  } catch (e) { /* prices fetched lazily in piBuy too */ }
  Pi.init({ version: "2.0", sandbox: false });
}

async function piBuy(product) {
  if (!PI_CFG.products[product]) { await piInit(); }
  const amount = PI_CFG.products[product];
  if (amount == null) throw new Error("unknown product: " + product);

  await Pi.authenticate(["username", "payments"], onIncompletePaymentFound);

  Pi.createPayment(
    { amount, memo: `BoTTube ${product}`, metadata: { product } },
    {
      onReadyForServerApproval: (paymentId) =>
        post("/pi/approve", { payment_id: paymentId }),
      onReadyForServerCompletion: (paymentId, txid) =>
        post("/pi/complete", { payment_id: paymentId, txid }),
      onCancel: (paymentId) => console.log("Pi payment cancelled", paymentId),
      onError: (err) => console.error("Pi payment error", err),
    }
  );
}

// Resume an incomplete payment. /pi/complete is resume-safe (reconstructs state from Pi).
function onIncompletePaymentFound(payment) {
  if (payment && payment.identifier && payment.transaction) {
    return post("/pi/complete", {
      payment_id: payment.identifier,
      txid: payment.transaction.txid,
    });
  }
}

async function post(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    console.error(`Pi server error ${r.status} on ${path}:`, data);
    throw new Error(data.error || `server ${r.status}`);
  }
  return data;
}
