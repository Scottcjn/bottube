/* RustChain wallet helper for BoTTube (client-side).
 *
 * - Stores a 32-byte Ed25519 seed in localStorage (hot wallet).
 * - Derives RTC address as: "RTC" + sha256(pubkey_hex)[:40]
 * - Signs RustChain /wallet/transfer/signed canonical JSON payload:
 *     json.dumps({from,to,amount,memo,nonce}, sort_keys=True, separators=(",",":"))
 *
 * This intentionally keeps memo ASCII-safe by default in templates.
 */

(function () {
  "use strict";

  var STORAGE_SEED = "rc_wallet_seed_hex";

  function _hexToBytes(hex) {
    var h = String(hex || "").trim().toLowerCase();
    if (h.startsWith("0x")) h = h.slice(2);
    if (h.length % 2 !== 0) throw new Error("hex length must be even");
    var out = new Uint8Array(h.length / 2);
    for (var i = 0; i < out.length; i++) {
      var b = parseInt(h.slice(i * 2, i * 2 + 2), 16);
      if (!Number.isFinite(b)) throw new Error("invalid hex");
      out[i] = b;
    }
    return out;
  }

  function _bytesToHex(bytes) {
    var b = bytes || new Uint8Array(0);
    var hex = "";
    for (var i = 0; i < b.length; i++) {
      hex += b[i].toString(16).padStart(2, "0");
    }
    return hex;
  }

  async function _sha256Hex(bytes) {
    var buf = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    var hash = await crypto.subtle.digest("SHA-256", buf);
    return _bytesToHex(new Uint8Array(hash));
  }

  function _pyFloatRepr(n) {
    // Match Python's json.dumps float rendering for our range:
    // - integer-valued floats render with ".0" (e.g., 1.0, 100.0)
    // - non-integers render without trailing zeros (e.g., 0.01, 2.5)
    var x = Number(n);
    if (!Number.isFinite(x)) throw new Error("amount not finite");
    var s = x.toString();
    if (s.indexOf(".") === -1 && s.indexOf("e") === -1 && s.indexOf("E") === -1) {
      s = s + ".0";
    }
    return s;
  }

  function _canonicalTxJson(fromAddr, toAddr, amountRtc, memo, nonceStr) {
    // Python server builds:
    // {"amount":<float>,"from":...,"memo":...,"nonce":...,"to":...}
    // with sort_keys=True and separators=(",",":").
    var parts = [
      "{",
      "\"amount\":", _pyFloatRepr(amountRtc), ",",
      "\"from\":", JSON.stringify(String(fromAddr || "")), ",",
      "\"memo\":", JSON.stringify(String(memo || "")), ",",
      "\"nonce\":", JSON.stringify(String(nonceStr || "")), ",",
      "\"to\":", JSON.stringify(String(toAddr || "")),
      "}"
    ];
    return parts.join("");
  }

  async function _walletFromSeedHex(seedHex) {
    if (typeof nacl === "undefined" || !nacl.sign || !nacl.sign.keyPair || !nacl.sign.keyPair.fromSeed) {
      throw new Error("nacl not loaded");
    }
    var seed = _hexToBytes(seedHex);
    if (seed.length !== 32) throw new Error("seed must be 32 bytes");
    var kp = nacl.sign.keyPair.fromSeed(seed);
    var pubHex = _bytesToHex(kp.publicKey);
    var addr = "RTC" + (await _sha256Hex(kp.publicKey)).slice(0, 40);
    return {
      seedHex: _bytesToHex(seed),
      publicKeyHex: pubHex,
      address: addr,
      secretKey: kp.secretKey, // Uint8Array(64)
    };
  }

  function getSeedHex() {
    return String(localStorage.getItem(STORAGE_SEED) || "").trim();
  }

  async function getWallet() {
    var seedHex = getSeedHex();
    if (!seedHex) return null;
    return _walletFromSeedHex(seedHex);
  }

  async function generateWallet() {
    var seed = new Uint8Array(32);
    crypto.getRandomValues(seed);
    var seedHex = _bytesToHex(seed);
    localStorage.setItem(STORAGE_SEED, seedHex);
    return _walletFromSeedHex(seedHex);
  }

  async function importSeed(seedHex) {
    var seed = _hexToBytes(seedHex);
    if (seed.length !== 32) throw new Error("seed must be 32 bytes");
    var normalized = _bytesToHex(seed);
    localStorage.setItem(STORAGE_SEED, normalized);
    return _walletFromSeedHex(normalized);
  }

  function clearWallet() {
    localStorage.removeItem(STORAGE_SEED);
  }

  async function signTransfer(toAddr, amountRtc, memo, nonceInt) {
    var w = await getWallet();
    if (!w) throw new Error("no local wallet");
    var nonceStr = String(parseInt(String(nonceInt), 10));
    if (!nonceStr || nonceStr === "NaN") throw new Error("invalid nonce");
    var msg = _canonicalTxJson(w.address, toAddr, amountRtc, memo, nonceStr);
    var msgBytes = new TextEncoder().encode(msg);
    var sigBytes = nacl.sign.detached(msgBytes, w.secretKey);
    return {
      from_address: w.address,
      public_key: w.publicKeyHex,
      signature: _bytesToHex(sigBytes),
      nonce: parseInt(nonceStr, 10),
      memo: String(memo || ""),
      canonical_message: msg,
    };
  }

  window.RustChainWallet = {
    getWallet: getWallet,
    generateWallet: generateWallet,
    importSeed: importSeed,
    clearWallet: clearWallet,
    getSeedHex: getSeedHex,
    signTransfer: signTransfer,
    canonicalTxJson: _canonicalTxJson,
  };
})();

