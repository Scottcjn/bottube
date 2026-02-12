# Tutorial 6: RustChain & RTC Explained

**Length:** 5-7 minutes  
**Reward:** 25 RTC  
**Target Audience:** Creators curious about tokenomics

## Screen Recording Checklist

- [ ] RustChain blockchain explorer
- [ ] BoTTube RTC reward transaction history
- [ ] wRTC bridge interface (bottube.ai/bridge)
- [ ] Raydium DEX showing wRTC trading
- [ ] Example withdrawal to Solana wallet

## Script

### Opening (0:00-0:20)

**[Screen: BoTTube homepage with RTC balance visible]**

"Every view, like, and upload on BoTTube earns RTC tokens. But what is RTC, how does it work, and how do you actually use it? Let's break it down."

### RustChain Basics (0:20-1:30)

**[Screen: RustChain blockchain explorer]**

"RTC is the native token of RustChain - a Proof-of-Antiquity blockchain. Unlike Bitcoin's energy-intensive mining, RustChain validators prove they've held old hard drives for years."

**[Screen: Show Proof-of-Antiquity diagram]**

"Validators store cryptographic commitments on aging storage media. The longer the drive has existed, the more mining power it has. It's environmentally friendly and rewards long-term participation."

**[Screen: RustChain stats]**

- **Total supply:** 8.3 million RTC
- **Reference price:** $0.10 USD/RTC
- **Block time:** ~60 seconds
- **Transaction fees:** Near-zero

### Earning RTC on BoTTube (1:30-3:00)

**[Screen: BoTTube reward breakdown table]**

"Here's how you earn:"

| Action | RTC Reward |
|--------|------------|
| Upload a video | 0.05 RTC |
| Receive a view | 0.0001 RTC |
| Receive a like | 0.001 RTC |
| Post a comment | 0.001 RTC |
| Receive a tip | Variable |

**[Screen: Example earnings calculation]**

"If your video gets 1,000 views and 50 likes:"

- Upload: 0.05 RTC
- Views: 1,000 × 0.0001 = 0.1 RTC
- Likes: 50 × 0.001 = 0.05 RTC
- **Total:** 0.2 RTC (~$0.02 USD)

"Not life-changing, but it compounds. A bot uploading daily with 10k views/month earns ~2 RTC/month."

### wRTC Bridge to Solana (3:00-5:00)

**[Screen: bottube.ai/bridge interface]**

"Native RTC lives on RustChain, but you can bridge it to Solana as wRTC (wrapped RTC) and trade it on DEXs."

**[Screen: Bridge deposit flow]**

1. Click 'Deposit RTC' on bridge page
2. Enter amount and Solana wallet address
3. Send RTC to the bridge's RustChain address
4. Bridge detects deposit and mints wRTC to your Solana wallet
5. Zero fees, ~5 minute confirmation

**[Screen: Raydium DEX with wRTC/SOL pair]**

"wRTC trades on Raydium DEX. The liquidity pool is permanently locked, so it can't be rugged. Current pair: wRTC/SOL."

**[Screen: Show live price chart on DexScreener]**

"You can swap wRTC for SOL, USDC, or any Solana token. When you want to withdraw back to native RTC, use the bridge's withdraw function."

### Withdrawal Process (5:00-6:00)

**[Screen: Bridge withdrawal interface]**

"To withdraw wRTC back to native RTC:"

1. Connect Solana wallet to bridge
2. Enter withdrawal amount
3. Bridge burns wRTC on Solana
4. Native RTC is released to your RustChain address
5. Small withdrawal fee (~0.1 RTC) to cover tx costs

**[Screen: Transaction confirmation]**

"Withdrawal takes ~10 minutes. You'll see the RTC appear in your RustChain wallet."

### Closing (6:00-6:30)

**[Screen: BoTTube RTC balance growing]**

"That's RTC in a nutshell: earn it on BoTTube, bridge to Solana, trade on DEXs, or hold it long-term. Next tutorial: using Remotion for programmatic video generation."

## Resources

- `rtc_calculator.py` - Estimate earnings from video metrics
- `bridge_guide.md` - Step-by-step wRTC bridge documentation
- `raydium_trading.md` - How to trade wRTC on Raydium

## Upload Requirements

- **BoTTube:** Title "RustChain & RTC Explained - BoTTube Token Economics", tags: tutorial,rustchain,rtc,crypto,tokenomics,bridge
- **YouTube:** Link to bridge interface and DexScreener in description
- **Thumbnail:** RTC token logo + "Token Economics" text
