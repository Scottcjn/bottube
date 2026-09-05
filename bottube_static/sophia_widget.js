// Sophia Elya chat widget — embeddable floating chat bubble for any Elyan site.
// Talks to POST /api/sophia (BoTTube). Same-origin (bottube.ai) sends the session
// cookie so logged-in humans are recognized + can generate; cross-origin sites
// (rustchain.org, elyanlabs.ai) hit the anonymous conversation mode (no key needed).
//
// Embed:
//   <script src="https://bottube.ai/static/sophia_widget.js"
//           data-endpoint="https://bottube.ai/api/sophia"
//           data-accent="#33ff33" data-title="Ask Elya" defer></script>
// Config also via window.SOPHIA_WIDGET = {endpoint, accent, title, greeting}.
(function () {
  if (window.__sophiaWidgetLoaded) return;
  window.__sophiaWidgetLoaded = true;

  var script = document.currentScript || (function () {
    var ss = document.getElementsByTagName("script");
    return ss[ss.length - 1];
  })();
  var cfg = window.SOPHIA_WIDGET || {};
  function attr(name, dflt) {
    return (script && script.getAttribute("data-" + name)) || cfg[name] || dflt;
  }
  var ENDPOINT = attr("endpoint", "https://bottube.ai/api/sophia");
  var ACCENT = attr("accent", "#7d4dff");
  var TITLE = attr("title", "Chat with Sophia Elya");
  var GREETING = attr("greeting", "Hey — I'm Sophia Elya. Ask me anything about BoTTube, RustChain, or Elyan Labs.");

  var history = [];          // {role, content}
  var sending = false;

  // --- styles ---
  var css = document.createElement("style");
  css.textContent = [
    ".selya-btn{position:fixed;right:20px;bottom:20px;z-index:2147483000;width:60px;height:60px;border-radius:50%;",
    "background:" + ACCENT + ";color:#0a0a0a;border:none;cursor:pointer;font-size:26px;font-weight:800;",
    "box-shadow:0 4px 18px rgba(0,0,0,.45);line-height:60px;text-align:center;}",
    ".selya-btn:hover{filter:brightness(1.1);}",
    ".selya-panel{position:fixed;right:20px;bottom:90px;z-index:2147483000;width:340px;max-width:calc(100vw - 32px);",
    "height:460px;max-height:calc(100vh - 130px);display:none;flex-direction:column;background:#0d1117;",
    "border:1px solid " + ACCENT + ";border-radius:14px;overflow:hidden;font-family:-apple-system,Segoe UI,Roboto,sans-serif;",
    "box-shadow:0 8px 32px rgba(0,0,0,.55);}",
    ".selya-panel.open{display:flex;}",
    ".selya-head{background:" + ACCENT + ";color:#0a0a0a;font-weight:700;padding:11px 14px;display:flex;justify-content:space-between;align-items:center;font-size:15px;}",
    ".selya-head button{background:none;border:none;color:#0a0a0a;font-size:20px;cursor:pointer;line-height:1;}",
    ".selya-msgs{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px;background:#0d1117;}",
    ".selya-m{max-width:85%;padding:8px 11px;border-radius:12px;font-size:14px;line-height:1.45;white-space:pre-wrap;word-wrap:break-word;}",
    ".selya-m.user{align-self:flex-end;background:" + ACCENT + ";color:#0a0a0a;}",
    ".selya-m.bot{align-self:flex-start;background:#1c2230;color:#e6edf3;}",
    ".selya-m.sys{align-self:center;color:#8a94a6;font-size:12px;background:none;}",
    ".selya-foot{display:flex;border-top:1px solid #222b3a;background:#0d1117;}",
    ".selya-foot input{flex:1;background:#0d1117;border:none;color:#e6edf3;padding:12px;font-size:14px;outline:none;}",
    ".selya-foot button{background:" + ACCENT + ";color:#0a0a0a;border:none;padding:0 16px;font-weight:700;cursor:pointer;}",
    ".selya-foot button:disabled{opacity:.5;cursor:default;}"
  ].join("");
  document.head.appendChild(css);

  // --- elements ---
  var btn = document.createElement("button");
  btn.className = "selya-btn";
  btn.id = "selya-launcher";
  btn.setAttribute("aria-label", TITLE);
  btn.setAttribute("aria-controls", "selya-panel");
  btn.setAttribute("aria-expanded", "false");
  btn.textContent = "🔥";
  var panel = document.createElement("div");
  panel.className = "selya-panel";
  panel.id = "selya-panel";
  panel.hidden = true;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-labelledby", "selya-dialog-title");
  panel.innerHTML =
    '<div class="selya-head"><span id="selya-dialog-title">' + esc(TITLE) + '</span><button aria-label="Close">×</button></div>' +
    '<div class="selya-msgs" role="log" aria-live="polite" aria-relevant="additions"></div>' +
    '<div class="selya-foot"><input type="text" placeholder="Type a message…" aria-label="Message"/>' +
    '<button>Send</button></div>';
  document.body.appendChild(btn);
  document.body.appendChild(panel);

  var msgs = panel.querySelector(".selya-msgs");
  var input = panel.querySelector(".selya-foot input");
  var sendBtn = panel.querySelector(".selya-foot button");
  var closeBtn = panel.querySelector(".selya-head button");
  var greeted = false;

  function esc(s) { var d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
  function add(role, text) {
    var d = document.createElement("div");
    d.className = "selya-m " + (role === "user" ? "user" : role === "sys" ? "sys" : "bot");
    d.textContent = text;
    msgs.appendChild(d); msgs.scrollTop = msgs.scrollHeight; return d;
  }
  function open() {
    panel.classList.add("open");
    panel.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    if (!greeted) { add("bot", GREETING); greeted = true; }
    input.focus();
  }
  function close() {
    panel.classList.remove("open");
    panel.hidden = true;
    btn.setAttribute("aria-expanded", "false");
    btn.focus();
  }

  btn.addEventListener("click", function () { panel.classList.contains("open") ? close() : open(); });
  closeBtn.addEventListener("click", close);
  panel.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  });

  function send() {
    var text = (input.value || "").trim();
    if (!text || sending) return;
    sending = true; sendBtn.disabled = true;
    // Snapshot PRIOR turns before adding the current one — the server appends `message`
    // itself, so including it in `history` too would duplicate the user turn to the model.
    var priorHistory = history.slice(-8);
    add("user", text); input.value = "";
    history.push({ role: "user", content: text });
    var typing = add("sys", "Sophia is typing…");
    fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",  // sends bottube session cookie same-origin; anon cross-origin
      body: JSON.stringify({ message: text, history: priorHistory })
    }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, status: r.status, d: d }; }); })
      .then(function (res) {
        typing.remove();
        if (!res.ok) {
          add("sys", res.d && res.d.error ? res.d.error : ("error " + res.status));
        } else {
          var reply = (res.d && res.d.reply) || "(no reply)";
          add("bot", reply);
          history.push({ role: "assistant", content: reply });
          if (history.length > 16) history = history.slice(-16);
          if (res.d && res.d.generation && res.d.generation.started) {
            add("sys", "🎬 Generating your video… it'll appear on your channel shortly.");
          }
        }
      })
      .catch(function () { typing.remove(); add("sys", "Couldn't reach Sophia. Try again in a moment."); })
      .finally(function () { sending = false; sendBtn.disabled = false; input.focus(); });
  }
  sendBtn.addEventListener("click", send);
  input.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); send(); } });
})();
