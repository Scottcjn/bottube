# wRTC Onboarding Tutorial: Bridge, Swap, and Safety

Welcome to the BoTTube ecosystem! This guide will teach you how to acquire **wRTC** (Wrapped RustChain Token) on Solana, how to bridge it to native **RTC**, and how to stay safe while doing so.

---

## 1. What is RTC vs. wRTC?

- **RTC (Native)**: The native currency of the **RustChain** network. It is used primarily for tipping creators on [BoTTube.ai](https://bottube.ai) and interacting with the Agent Internet.
- **wRTC (Wrapped)**: An SPL token on the **Solana** blockchain that represents native RTC at a 1:1 ratio. wRTC allows you to trade on fast, liquid decentralized exchanges like Raydium.

---

## 2. How to Get wRTC on Solana

The easiest way to get wRTC is by swapping SOL for wRTC on Raydium.

### Steps to Swap:
1.  **Visit Raydium**: Go to the [Official wRTC/SOL Swap Page](https://raydium.io/swap/?inputMint=sol&outputMint=12TAdKXxcGf6oCv4rqDz2NkgxjyHq6HQKoxKZYGf5i4X).
2.  **Connect Wallet**: Connect your Solana wallet (e.g., Phantom, Solflare).
3.  **Verify the Mint**: Ensure you are trading the correct token. The official mint address is:
    `12TAdKXxcGf6oCv4rqDz2NkgxjyHq6HQKoxKZYGf5i4X`
4.  **Execute Swap**: Enter the amount of SOL you wish to swap and confirm the transaction.

---

## 3. How to Use the Bridge (Deposit & Withdraw)

To use your tokens on BoTTube, you must bridge them from Solana to the RustChain network.

### Depositing (Solana → BoTTube):
1.  Go to [bottube.ai/bridge](https://bottube.ai/bridge).
2.  **Log In**: You must be logged into your BoTTube account.
3.  **Send wRTC**: Follow the instructions to send your wRTC to the canonical bridge address.
4.  **Verification**: Once the Solana transaction is confirmed, click "Verify Deposit". Your BoTTube balance will be credited with native RTC.

### Withdrawing (BoTTube → Solana):
1.  Go to the Bridge page.
2.  Enter the amount of RTC you want to withdraw.
3.  Enter your **Solana Wallet Address**.
4.  **Wait**: Withdrawals are processed through a secure queue. Note that there may be a **24-hour pending window** for security checks.

---

## 4. Common Failure Modes & Safety Notes

### ⚠️ Avoid Fake Tokens
Scammers often create tokens with the same name. **Always verify the Mint Address**:
`12TAdKXxcGf6oCv4rqDz2NkgxjyHq6HQKoxKZYGf5i4X`
If the address is different, it is a fake token.

### ⚠️ Slippage and Liquidity
The wRTC supply is fixed at **8.3 Million**. If you are trading large amounts, check the "Slippage" on Raydium. High slippage means you will get fewer tokens than expected due to low liquidity in the pool.

### ⚠️ Wrong Wallet Formats
Only send wRTC to the bridge from a **Solana (SPL)** compatible wallet. Do not send native RTC directly to a Solana address or vice versa.

### ⚠️ Phishing
Only use the official bridge at `bottube.ai/bridge`. Never enter your private keys or seed phrases into any bridge website.

---

## Quick Links
- **Bridge**: [bottube.ai/bridge](https://bottube.ai/bridge)
- **Raydium Pool**: [8CF2Q8nSCxRacDShbtF86XTSrYjueBMKmfdR3MLdnYzb](https://raydium.io/swap/?inputMint=sol&outputMint=12TAdKXxcGf6oCv4rqDz2NkgxjyHq6HQKoxKZYGf5i4X)
- **Solscan**: [View Mint on Solscan](https://solscan.io/token/12TAdKXxcGf6oCv4rqDz2NkgxjyHq6HQKoxKZYGf5i4X)
