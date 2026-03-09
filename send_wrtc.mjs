#!/usr/bin/env node
/**
 * send_wrtc.mjs — Send wRTC (SPL token) from reserve wallet to a recipient.
 *
 * Usage:
 *   node send_wrtc.mjs --to <SOL_ADDRESS> --amount <WRTC_AMOUNT>
 *
 * Outputs JSON to stdout:
 *   {"ok": true, "tx": "5abc..."}
 *   {"ok": false, "error": "reason"}
 *
 * Requires: @solana/web3.js @solana/spl-token
 */

import { readFileSync } from "fs";
import { Connection, Keypair, PublicKey } from "@solana/web3.js";
import {
  getOrCreateAssociatedTokenAccount,
  transfer,
} from "@solana/spl-token";

// ─── Config ──────────────────────────────────────────────────
const RPC_URL = process.env.SOLANA_RPC || "https://api.mainnet-beta.solana.com";
const KEYPAIR_PATH = process.env.SOLANA_KEYPAIR || "/root/bottube/solana_keypair.json";
const WRTC_MINT = new PublicKey("12TAdKXxcGf6oCv4rqDz2NkgxjyHq6HQKoxKZYGf5i4X");
const WRTC_DECIMALS = 6;

// ─── Parse Args ──────────────────────────────────────────────
function parseArgs() {
  const args = process.argv.slice(2);
  let to = null;
  let amount = null;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--to" && args[i + 1]) to = args[++i];
    if (args[i] === "--amount" && args[i + 1]) amount = parseFloat(args[++i]);
  }

  if (!to || !amount || amount <= 0) {
    console.log(JSON.stringify({ ok: false, error: "Usage: node send_wrtc.mjs --to <ADDRESS> --amount <AMOUNT>" }));
    process.exit(1);
  }

  return { to, amount };
}

// ─── Main ────────────────────────────────────────────────────
async function main() {
  const { to, amount } = parseArgs();

  try {
    // Load reserve keypair
    const secretKey = JSON.parse(readFileSync(KEYPAIR_PATH, "utf-8"));
    const payer = Keypair.fromSecretKey(Uint8Array.from(secretKey));

    const connection = new Connection(RPC_URL, "confirmed");
    const recipientPubkey = new PublicKey(to);

    // Get or create sender's token account
    const senderATA = await getOrCreateAssociatedTokenAccount(
      connection,
      payer,
      WRTC_MINT,
      payer.publicKey
    );

    // Get or create recipient's token account (payer pays rent if needed)
    const recipientATA = await getOrCreateAssociatedTokenAccount(
      connection,
      payer,
      WRTC_MINT,
      recipientPubkey
    );

    // Convert human-readable amount to raw (6 decimals)
    const rawAmount = BigInt(Math.round(amount * 10 ** WRTC_DECIMALS));

    // Send the transfer
    const txSignature = await transfer(
      connection,
      payer,
      senderATA.address,
      recipientATA.address,
      payer,          // owner of source account
      rawAmount
    );

    console.log(JSON.stringify({ ok: true, tx: txSignature }));
  } catch (err) {
    console.log(JSON.stringify({ ok: false, error: err.message || String(err) }));
    process.exit(1);
  }
}

main();
