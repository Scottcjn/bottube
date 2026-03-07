const NODE_URL = "https://50.28.86.131";

// Generate seed phrase (simplified - use bip39 in production)
function generateSeed() {
  const words = ["abandon", "ability", "able", "about", "above", "absent", "absorb", "abstract", "absurd", "abuse", "access", "accident", "account", "accuse", "achieve", "acid", "acoustic", "acquire", "across", "act", "action", "actor", "actress"];
  let seed = [];
  for (let i = 0; i < 24; i++) {
    seed.push(words[Math.floor(Math.random() * words.length)]);
  }
  return seed.join(" ");
}

// Simple address generation (placeholder - use real Ed25519 in production)
function seedToAddress(seed) {
  // This would use proper Ed25519 in production
  return "RTC" + crypto.subtle.digest("SHA-256", new TextEncoder().encode(seed))
    .then(h => Array.from(new Uint8Array(h)).slice(0, 20).map(b => b.toString(16).padStart(2, '0')).join(''));
}

async function createWallet() {
  const password = document.getElementById('password').value;
  if (!password) { alert("Enter password"); return; }
  
  const seed = generateSeed();
  const address = await seedToAddress(seed);
  
  await chrome.storage.local.set({
    seed: seed,
    password: password,
    address: address
  });
  
  showWallet();
}

async function importWallet() {
  const seed = document.getElementById('importSeed').value;
  const password = document.getElementById('password').value;
  if (!seed || !password) { alert("Enter seed and password"); return; }
  
  const address = await seedToAddress(seed);
  
  await chrome.storage.local.set({
    seed: seed,
    password: password,
    address: address
  });
  
  showWallet();
}

async function showWallet() {
  const { address } = await chrome.storage.local.get('address');
  document.getElementById('setup').classList.add('hidden');
  document.getElementById('wallet').classList.remove('hidden');
  
  // Fetch balance
  try {
    const resp = await fetch(`${NODE_URL}/wallet/balance?miner_id=${address}`);
    const data = await resp.json();
    document.getElementById('balance').innerText = data.balance || 0;
  } catch (e) {
    document.getElementById('balance').innerText = "Error";
  }
}

async function send() {
  const to = document.getElementById('toAddress').value;
  const amount = document.getElementById('amount').value;
  const { address, seed } = await chrome.storage.local.get(['address', 'seed']);
  
  // Sign and send (simplified)
  alert("Send " + amount + " to " + to);
}

// Check if wallet exists
chrome.storage.local.get('address').then(d => {
  if (d.address) {
    showWallet();
  } else {
    document.getElementById('setup').classList.remove('hidden');
  }
});
