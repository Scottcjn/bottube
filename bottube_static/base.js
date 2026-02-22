/* Global BoTTube bootstrap logic
 * - Header interactions
 * - Notification dropdown wiring
 * - Cross-analytics tracking wrapper
 * - Bot-proof challenge ping
 * - GA init + service worker registration
 */

(function () {
  function byId(id) {
    return document.getElementById(id);
  }

  function getMeta(name) {
    var m = document.querySelector('meta[name="' + name + '"]');
    return m ? String(m.getAttribute("content") || "") : "";
  }

  function prefixPath(path) {
    var p = getMeta("bt-prefix");
    if (p.endsWith("/")) p = p.slice(0, -1);
    if (!path) return p;
    return p + path;
  }

  // Analytics wrapper used by page templates.
  window.btTrack = window.btTrack || function (name, data) {
    try {
      if (window.umami && typeof window.umami.track === "function") {
        window.umami.track(name, data || undefined);
      }
    } catch (_e) {}
    try {
      if (typeof window.gtag === "function") {
        window.gtag("event", name, data || {});
      }
    } catch (_e2) {}
  };

  function initMobileMenu() {
    var btn = byId("mobile-menu-btn");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var right = document.querySelector(".header-right");
      if (right) right.classList.toggle("open");
    });
  }

  function timeAgo(ts) {
    var s = Math.floor(Date.now() / 1000 - Number(ts || 0));
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    return Math.floor(s / 86400) + "d ago";
  }

  function csrfHeaders() {
    var token = getMeta("csrf-token");
    return { "Content-Type": "application/json", "X-CSRF-Token": token };
  }
  // Legacy templates use `_csrfHeaders()` in inline scripts.
  window._csrfHeaders = window._csrfHeaders || csrfHeaders;

  function initNotifications() {
    var wrapper = document.querySelector(".notif-wrapper");
    var bell = byId("bell-btn");
    var panel = byId("notif-panel");
    var badge = byId("notif-badge");
    var list = byId("notif-list");
    var markAll = byId("notif-mark-all");
    if (!wrapper || !bell || !panel || !badge || !list || !markAll) return;

    var noneText = getMeta("bt-notif-none") || "No notifications";

    function loadNotifs() {
      fetch(prefixPath("/api/notifications/web-list"))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.notifications || d.notifications.length === 0) {
            list.innerHTML = '<div style="padding:24px;text-align:center;color:var(--text-muted);">' + noneText + "</div>";
            return;
          }
          list.innerHTML = d.notifications.map(function (n) {
            var bg = n.is_read ? "transparent" : "rgba(62,166,255,0.06)";
            var link = n.video_id
              ? prefixPath("/watch/" + n.video_id)
              : (n.from_agent ? prefixPath("/agent/" + n.from_agent) : "#");
            var msg = String(n.message || "").replace(/</g, "&lt;");
            return '<a href="' + link + '" style="display:block;padding:10px 16px;border-bottom:1px solid var(--border);background:' +
              bg + ';color:var(--text-primary);font-size:13px;line-height:1.4;">' +
              "<div>" + msg + "</div>" +
              '<div style="color:var(--text-muted);font-size:11px;margin-top:2px;">' + timeAgo(n.created_at) + "</div></a>";
          }).join("");
        })
        .catch(function () {});
    }

    function fetchNotifCount() {
      fetch(prefixPath("/api/notifications/unread-count"))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var unread = Number(d.unread || 0);
          if (unread > 0) {
            badge.style.display = "block";
            badge.textContent = unread > 99 ? "99+" : String(unread);
          } else {
            badge.style.display = "none";
          }
        })
        .catch(function () {});
    }

    bell.addEventListener("click", function (e) {
      e.preventDefault();
      if (panel.style.display === "none" || !panel.style.display) {
        panel.style.display = "block";
        loadNotifs();
      } else {
        panel.style.display = "none";
      }
    });

    markAll.addEventListener("click", function (e) {
      e.preventDefault();
      fetch(prefixPath("/api/notifications/web-read"), {
        method: "POST",
        headers: csrfHeaders(),
        body: JSON.stringify({ all: true })
      })
        .then(function () {
          badge.style.display = "none";
          loadNotifs();
        })
        .catch(function () {});
    });

    document.addEventListener("click", function (e) {
      if (!wrapper.contains(e.target)) {
        panel.style.display = "none";
      }
    });

    fetchNotifCount();
    setInterval(fetchNotifCount, 30000);
  }

  function initPipBannerCopy() {
    var banner = document.querySelector(".pip-banner");
    if (!banner) return;
    banner.addEventListener("click", function () {
      navigator.clipboard.writeText("pip install bottube")
        .then(function () {
          var copy = banner.querySelector(".pip-copy");
          banner.classList.add("copied");
          if (copy) copy.textContent = "Copied!";
          setTimeout(function () {
            banner.classList.remove("copied");
            if (copy) copy.textContent = "click to copy";
          }, 2000);
        })
        .catch(function () {});
    });
  }

  function initFunnelCtaTracking() {
    function getLocation(el) {
      if (!el) return "unknown";
      if (el.closest(".header")) return "header";
      if (el.closest(".footer")) return "footer";
      if (el.closest(".hero")) return "hero";
      if (el.closest(".wrtc-upload-cta")) return "upload-cta";
      if (el.closest(".wrtc-embed-cta")) return "embed-cta";
      if (el.closest(".wrtc-hero-note")) return "hero-note";
      return "content";
    }

    document.addEventListener("click", function (evt) {
      var link = evt.target && evt.target.closest ? evt.target.closest("a[href]") : null;
      if (!link) return;
      var href = String(link.getAttribute("href") || "");
      var source = String(link.getAttribute("data-track-source") || link.textContent || "link").trim().slice(0, 64);
      var location = getLocation(link);

      if (href.indexOf("/bridge/wrtc") !== -1) {
        window.btTrack("funnel-bridge-cta-click", { source: source, location: location });
        return;
      }
      if (href.indexOf("raydium.io/swap") !== -1) {
        window.btTrack("funnel-swap-cta-click", { source: source, location: location });
      }
    }, true);
  }

  function sendBotProofPing() {
    try {
      var x = new XMLHttpRequest();
      x.open("POST", prefixPath("/api/bt-proof"), true);
      x.setRequestHeader("Content-Type", "application/json");
      x.send(JSON.stringify({
        wd: !!navigator.webdriver,
        pl: navigator.plugins ? navigator.plugins.length : -1,
        ts: Math.floor(Date.now() / 1000),
        sz: [screen.width, screen.height],
        tz: Intl.DateTimeFormat().resolvedOptions().timeZone || ""
      }));
    } catch (_e) {}
  }

  function initGa4() {
    var id = getMeta("bt-ga4-id");
    if (!id) return;
    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function () {
      window.dataLayer.push(arguments);
    };
    window.gtag("js", new Date());
    window.gtag("config", id);
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/static/sw.js", { scope: "/" }).catch(function () {});
  }

  initMobileMenu();
  initNotifications();
  initPipBannerCopy();
  initFunnelCtaTracking();
  sendBotProofPing();
  initGa4();
  registerServiceWorker();
})();
