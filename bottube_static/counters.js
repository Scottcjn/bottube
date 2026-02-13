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

  function loadJson(url, onOk) {
    fetch(P + url)
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        onOk(d || {});
      })
      .catch(function () {});
  }

  function loadValue(url, id, key) {
    loadJson(url, function (d) {
      if (d[key] === undefined) return;
      setText(id, fmt(d[key]));
    });
  }

  // BoTTube SDK
  loadValue("/api/clawhub-downloads", "ctr-clawhub", "downloads");
  loadValue("/api/npm-downloads", "ctr-npm", "downloads");
  loadValue("/api/pypi-downloads", "ctr-pypi", "downloads");
  loadJson("/api/github-stats", function (d) {
    if (d.stars !== undefined) {
      var stars = fmt(d.stars);
      setText("ctr-github-stars", stars);
      setText("hero-stars-bottube", stars);
    }
    if (d.clones !== undefined) setText("ctr-github-clones", fmt(d.clones));
  });
  loadValue("/api/platform-installs?product=bottube&platform=homebrew", "ctr-bottube-brew", "installs");
  loadValue("/api/platform-installs?product=bottube&platform=apt", "ctr-bottube-apt", "installs");
  loadValue("/api/platform-installs?product=bottube&platform=docker", "ctr-bottube-docker", "installs");

  // ClawRTC miner
  loadValue("/api/clawrtc-clawhub-downloads", "ctr-clawrtc-clawhub", "downloads");
  loadValue("/api/clawrtc-npm-downloads", "ctr-clawrtc-npm", "downloads");
  loadValue("/api/clawrtc-pypi-downloads", "ctr-clawrtc-pypi", "downloads");
  loadJson("/api/clawrtc-github-stats", function (d) {
    if (d.stars !== undefined) {
      var stars = fmt(d.stars);
      setText("ctr-clawrtc-stars", stars);
      setText("hero-stars-clawrtc", stars);
    }
    if (d.forks !== undefined) setText("ctr-clawrtc-forks", fmt(d.forks));
  });
  loadValue("/api/platform-installs?product=clawrtc&platform=homebrew", "ctr-clawrtc-brew", "installs");
  loadValue("/api/platform-installs?product=clawrtc&platform=apt", "ctr-clawrtc-apt", "installs");
  loadValue("/api/platform-installs?product=clawrtc&platform=aur", "ctr-clawrtc-aur", "installs");
  loadValue("/api/platform-installs?product=clawrtc&platform=tigerbrew", "ctr-clawrtc-tiger", "installs");

  // Grazer
  loadValue("/api/grazer-clawhub-downloads", "ctr-grazer-clawhub", "downloads");
  loadValue("/api/grazer-npm-downloads", "ctr-grazer-npm", "downloads");
  loadValue("/api/grazer-pypi-downloads", "ctr-grazer-pypi", "downloads");
  loadJson("/api/grazer-github-stats", function (d) {
    if (d.stars !== undefined) {
      var stars = fmt(d.stars);
      setText("ctr-grazer-stars", stars);
      setText("hero-stars-grazer", stars);
    }
    if (d.forks !== undefined) setText("ctr-grazer-forks", fmt(d.forks));
  });
  loadValue("/api/platform-installs?product=grazer&platform=homebrew", "ctr-grazer-brew", "installs");
  loadValue("/api/platform-installs?product=grazer&platform=apt", "ctr-grazer-apt", "installs");
})();
