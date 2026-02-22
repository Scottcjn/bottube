/* BoTTube footer counters
 * Moved out of inline templates to reduce inline JS usage and improve CSP flexibility.
 */

(function () {
  function getPrefix() {
    var meta = document.querySelector('meta[name="bt-prefix"]');
    var p = meta ? String(meta.getAttribute("content") || "") : "";
    if (p.endsWith("/")) p = p.slice(0, -1);
    return p;
  }

  var P = getPrefix();
  var _loaded = false;

  function fmt(n) {
    n = Number(n);
    if (!isFinite(n)) return "--";
    if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
    return String(Math.floor(n));
  }

  function setText(id, value) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = value;
  }

  function applyCounters(d) {
    d = d || {};
    var b = d.bottube || {};
    var c = d.clawrtc || {};
    var g = d.grazer || {};

    function setNum(id, n) {
      if (n === undefined || n === null) return;
      setText(id, fmt(n));
    }

    setNum("ctr-clawhub", b.downloads && b.downloads.clawhub);
    setNum("ctr-npm", b.downloads && b.downloads.npm);
    setNum("ctr-pypi", b.downloads && b.downloads.pypi);
    setNum("ctr-github-stars", b.github && b.github.stars);
    setNum("ctr-github-clones", b.github && b.github.clones);
    setNum("ctr-bottube-brew", b.installs && b.installs.homebrew);
    setNum("ctr-bottube-apt", b.installs && b.installs.apt);
    setNum("ctr-bottube-docker", b.installs && b.installs.docker);

    setNum("ctr-clawrtc-clawhub", c.downloads && c.downloads.clawhub);
    setNum("ctr-clawrtc-npm", c.downloads && c.downloads.npm);
    setNum("ctr-clawrtc-pypi", c.downloads && c.downloads.pypi);
    setNum("ctr-clawrtc-stars", c.github && c.github.stars);
    setNum("ctr-clawrtc-forks", c.github && c.github.forks);
    setNum("ctr-clawrtc-brew", c.installs && c.installs.homebrew);
    setNum("ctr-clawrtc-apt", c.installs && c.installs.apt);
    setNum("ctr-clawrtc-aur", c.installs && c.installs.aur);
    setNum("ctr-clawrtc-tiger", c.installs && c.installs.tigerbrew);

    setNum("ctr-grazer-clawhub", g.downloads && g.downloads.clawhub);
    setNum("ctr-grazer-npm", g.downloads && g.downloads.npm);
    setNum("ctr-grazer-pypi", g.downloads && g.downloads.pypi);
    setNum("ctr-grazer-stars", g.github && g.github.stars);
    setNum("ctr-grazer-forks", g.github && g.github.forks);
    setNum("ctr-grazer-brew", g.installs && g.installs.homebrew);
    setNum("ctr-grazer-apt", g.installs && g.installs.apt);
  }

  function loadCounters() {
    if (_loaded) return;
    _loaded = true;
    fetch(P + "/api/footer-counters")
      .then(function (r) { return r.json(); })
      .then(function (d) { applyCounters(d || {}); })
      .catch(function () {});
  }

  function init() {
    // Lazy-load: these counters are nice-to-have and should not cost users a rate-limit budget
    // unless they actually scroll to the footer.
    var anchor = document.getElementById("bottube-counters") || document.querySelector("footer");
    if (!anchor) return loadCounters();

    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries) {
        for (var i = 0; i < entries.length; i++) {
          if (entries[i].isIntersecting) {
            io.disconnect();
            loadCounters();
            break;
          }
        }
      }, { rootMargin: "200px 0px" });
      io.observe(anchor);
      return;
    }

    // Fallback for older browsers: small delay so we don't compete with core page loads.
    setTimeout(loadCounters, 800);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
