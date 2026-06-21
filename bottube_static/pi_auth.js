// Pi Network login + Pi-Browser gating. Load after https://sdk.minepi.com/pi-sdk.js
// PI-ONLY UI: give any element class="pi-only" — hidden everywhere EXCEPT inside
// Pi Browser (revealed only after Pi.authenticate() succeeds, which only works there).
//
// NOTE on sandbox: `sandbox: true` is ONLY for the desktop Pi Sandbox
// (sandbox.minepi.com). Inside the real Pi Browser app it MUST be false, or the
// native auth bridge is never reached and authenticate() silently fails. Testnet
// vs Mainnet is decided by the app config in the Pi Developer Portal, not this flag.
(function () {
  var st = document.createElement("style");
  st.textContent = ".pi-only{display:none !important} body.pi-browser .pi-only{display:revert !important}";
  (document.head || document.documentElement).appendChild(st);

  // Fire-and-forget diagnostic beacon (shows up in server access log as /pi/diag?...).
  function diag(stage, extra) {
    try {
      new Image().src = "/pi/diag?stage=" + encodeURIComponent(stage) +
        "&pi=" + (typeof Pi) +
        (extra != null ? "&x=" + encodeURIComponent(String(extra)).slice(0, 140) : "") +
        "&t=" + Date.now();
    } catch (e) {}
  }

  var _init;
  function piInit() { if (!_init) { _init = Promise.resolve(Pi.init({ version: "2.0", sandbox: false })); } return _init; }

  async function piSignIn() {
    if (typeof Pi === "undefined") { diag("no_pi"); console.warn("Pi SDK not loaded"); return; }
    diag("init");
    await piInit();
    diag("auth_start");
    // Fail fast if the native bridge doesn't answer (Pi's own timeout is 120s, which
    // looks frozen). If this rejects with "bridge_timeout", the app almost certainly
    // isn't opened as an APPROVED Pi app from the Developer Portal.
    var auth = await Promise.race([
      Pi.authenticate(["username"], onIncompletePaymentFound),
      new Promise(function (_, rej) { setTimeout(function () { rej(new Error("bridge_timeout")); }, 12000); })
    ]);
    diag("auth_ok");   // do NOT log the username (PII in access logs)
    var res = await fetch("/pi/auth", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: auth.accessToken })
    });
    diag("server", res.status);
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok) { console.error("Pi auth failed:", data); throw new Error(data.error || ("server " + res.status)); }
    document.body.classList.add("pi-browser");   // confirmed Pi Browser -> reveal pi-only UI
    console.log("Pi signed in as:", data.username);
    document.dispatchEvent(new CustomEvent("pi:authenticated", { detail: data }));
    // Session cookie is now set server-side; reload ONCE so the page renders
    // logged-in. sessionStorage guard prevents a reload loop.
    try {
      if (!sessionStorage.getItem("pi_session_synced")) {
        sessionStorage.setItem("pi_session_synced", "1");
        window.location.reload();
        return data;
      }
    } catch (e) { /* sessionStorage unavailable -> skip reload */ }
    return data;
  }
  function onIncompletePaymentFound(p) { console.log("Incomplete Pi payment:", p && p.identifier); }

  window.piSignIn = piSignIn;
  window.isPiBrowser = function () { return document.body.classList.contains("pi-browser"); };

  // Confirm we are REALLY inside Pi Browser without the 120s auth hang:
  // Pi.nativeFeaturesList() resolves quickly via the native bridge in Pi Browser,
  // and rejects/never-arrives elsewhere (we cap it with a short race).
  function confirmPiBrowser() {
    return piInit().then(function () {
      if (!Pi || typeof Pi.nativeFeaturesList !== "function") return Promise.reject(new Error("no_nfl"));
      return Promise.race([
        Pi.nativeFeaturesList(),
        new Promise(function (_, rej) { setTimeout(function () { rej(new Error("nfl_timeout")); }, 4000); })
      ]);
    });
  }

  function onPiPath() {
    return location.pathname === "/pi" || location.pathname.indexOf("/pi/") === 0;
  }

  window.addEventListener("load", function () {
    diag("load");
    if (window.PI_AUTO_SIGNIN === false) { diag("skip_logged_in"); return; }
    if (typeof Pi === "undefined") { diag("no_pi_at_load"); return; }
    confirmPiBrowser().then(function () {
      // Confirmed Pi Browser. Reveal pi-only UI everywhere.
      document.body.classList.add("pi-browser");
      diag("pi_confirmed");
      // Immediate routing: push Pioneers to the Pi-friendly storefront — but ONLY
      // from the home page. Deep links inside Pi Browser (/watch, /search, /agent,
      // account flows) must NOT be hijacked. The Pi app should also be registered to
      // https://bottube.ai/pi so first launch lands there directly.
      // Only redirect to /pi on the real apex host. If the app was opened via a Pi
      // subdomain (e.g. *.pinet.com), a relative redirect to /pi may not be proxied —
      // so stay put and just sign in in place.
      if (location.pathname === "/" && /(^|\.)bottube\.ai$/i.test(location.hostname)) {
        var redirected = false;
        try { redirected = !!sessionStorage.getItem("pi_redirected"); } catch (e) {}
        if (!redirected) {
          try { sessionStorage.setItem("pi_redirected", "1"); } catch (e) {}
          diag("redirect_pi");
          location.replace("/pi");
          return;
        }
      }
      // On /pi, or a deep link, or redirect already used -> sign in (no navigation).
      piSignIn().catch(function (e) { diag("auth_err", e && e.message); console.error("Pi auto sign-in:", e); });
    }).catch(function (e) {
      // Not Pi Browser (or bridge unavailable) -> standard RTC site, do nothing.
      diag("not_pi", e && e.message);
    });
  });
})();
