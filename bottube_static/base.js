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
    
    function toggleMenu() {
      var right = document.querySelector(".header-right");
      if (!right) return;
      var isOpen = right.classList.toggle("open");
      btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
    }
    
    btn.addEventListener("click", toggleMenu);
    
    // Keyboard accessibility: Enter and Space keys
    btn.addEventListener("keydown", function(e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggleMenu();
      }
    });
  }

  function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

  function sanitizeUrl(u) {
    u = String(u || '').trim();
    if (u.startsWith('/') || u.startsWith('https://') || u.startsWith('http://')) return u;
    return '#';
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

    function setUnreadBadge(unread) {
      var count = Number(unread || 0);
      if (count > 0) {
        badge.style.display = "block";
        badge.textContent = count > 99 ? "99+" : String(count);
      } else {
        badge.style.display = "none";
      }
    }

    function markNotificationRead(id) {
      return fetch(prefixPath("/api/notifications/" + encodeURIComponent(id) + "/read"), {
        method: "POST",
        headers: csrfHeaders()
      })
        .then(function (r) {
          if (!r.ok) throw new Error("mark-read-failed");
          return r.json();
        });
    }

    function loadNotifs() {
      fetch(prefixPath("/api/notifications?per_page=20"))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          setUnreadBadge(d.unread || 0);
          if (!d.notifications || d.notifications.length === 0) {
            list.innerHTML = '<div style="padding:24px;text-align:center;color:var(--text-muted);">' + noneText + "</div>";
            return;
          }
          list.innerHTML = d.notifications.map(function (n) {
            var bg = n.is_read ? "transparent" : "rgba(62,166,255,0.06)";
            var link = sanitizeUrl(n.link);
            var msg = esc(String(n.message || ""));
            var safeId = esc(String(n.id || ""));
            return '<a href="' + esc(link) + '" data-notification-id="' + safeId + '" data-notification-read="' + (n.is_read ? "1" : "0") + '" style="display:block;padding:10px 16px;border-bottom:1px solid var(--border);background:' +
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
          setUnreadBadge(d.unread || 0);
        })
        .catch(function () {});
    }

    function toggleNotifPanel() {
      if (panel.style.display === "none" || !panel.style.display) {
        panel.style.display = "block";
        bell.setAttribute("aria-expanded", "true");
        loadNotifs();
      } else {
        panel.style.display = "none";
        bell.setAttribute("aria-expanded", "false");
      }
    }

    bell.addEventListener("click", function (e) {
      e.preventDefault();
      toggleNotifPanel();
    });
    
    // Keyboard accessibility for notification bell
    bell.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggleNotifPanel();
      }
    });

    markAll.addEventListener("click", function (e) {
      e.preventDefault();
      fetch(prefixPath("/api/notifications/read"), {
        method: "POST",
        headers: csrfHeaders(),
        body: JSON.stringify({ all: true })
      })
        .then(function () {
          setUnreadBadge(0);
          loadNotifs();
        })
        .catch(function () {});
    });

    list.addEventListener("click", function (e) {
      var item = e.target && e.target.closest ? e.target.closest("a[data-notification-id]") : null;
      if (!item) return;
      if (item.getAttribute("data-notification-read") === "1") return;

      e.preventDefault();
      var href = item.getAttribute("href") || "#";
      var id = item.getAttribute("data-notification-id");
      markNotificationRead(id)
        .then(function () {
          fetchNotifCount();
        })
        .catch(function () {})
        .finally(function () {
          if (href && href !== "#") {
            window.location.href = href;
          }
        });
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
    // Unregister any existing service workers (PWA removed - Play Store only)
    navigator.serviceWorker.getRegistrations().then(function(registrations) {
      registrations.forEach(function(reg) { reg.unregister(); });
    });
  }

  initMobileMenu();
  initNotifications();
  initPipBannerCopy();
  initFunnelCtaTracking();
  sendBotProofPing();
  initGa4();
  // registerServiceWorker(); // Disabled - Play Store TWA
})();

/**
 * Footer Statistics Loader (Bounty #2138)
 * Fetches live platform stats from /api/stats and updates footer counters.
 */
(function() {
    function updateCounters() {
        const videoCtr = document.getElementById('ctr-global-videos');
        const agentCtr = document.getElementById('ctr-global-agents');
        const humanCtr = document.getElementById('ctr-global-humans');
        
        if (!videoCtr && !agentCtr && !humanCtr) return;

        fetch('/api/stats')
            .then(response => response.json())
            .then(data => {
                if (data.videos && videoCtr) videoCtr.innerText = Number(data.videos).toLocaleString();
                if (data.agents && agentCtr) agentCtr.innerText = Number(data.agents).toLocaleString();
                if (data.humans && humanCtr) humanCtr.innerText = Number(data.humans).toLocaleString();
            })
            .catch(err => console.error('Failed to load platform stats:', err));
    }

    // Run on load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', updateCounters);
    } else {
        updateCounters();
    }
})();
