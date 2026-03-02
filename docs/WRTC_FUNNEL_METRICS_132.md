# wRTC Conversion Funnel Improvements — #132

## Baseline
Before this patch, wRTC bridge pages had partial funnel events, but global CTA clicks (header/footer/home hero/upload/embed) were not consistently tracked under a unified schema.

## Changes
- Added delegated global CTA tracking in `bottube_static/base.js` for:
  - `funnel-bridge-cta-click`
  - `funnel-swap-cta-click`
- Event metadata now includes:
  - `source` (link text or explicit `data-track-source`)
  - `location` (`header`, `footer`, `hero`, `upload-cta`, `embed-cta`, `hero-note`, `content`)
- Existing bridge-level funnel events remain active (view, deposit/withdraw start/success/fail, history view, chain switch).

## Event Map
1. Discovery / intent
   - `funnel-bridge-cta-click`
   - `funnel-swap-cta-click`
2. Bridge entry
   - `funnel-bridge-view`
   - `funnel-bridge-switch-chain`
3. Conversion actions
   - `funnel-wrtc-buy-click`
   - `funnel-wrtc-deposit-start`
   - `funnel-wrtc-deposit-ok` / `funnel-wrtc-deposit-fail`
   - `funnel-wrtc-withdraw-start`
   - `funnel-wrtc-withdraw-ok` / `funnel-wrtc-withdraw-fail`

## Privacy Notes
- No private keys, seed phrases, or full wallet secrets are tracked.
- Only high-level UX event names and non-sensitive context fields (`source`, `location`) are sent.
- Existing analytics providers (`umami`, `gtag`) are used through `window.btTrack`.

## Post-change measurement plan
Track 7-day movement for:
- CTR to bridge: `funnel-bridge-cta-click`
- CTR to swap: `funnel-swap-cta-click`
- Bridge view-to-deposit-start rate:
  - `funnel-wrtc-deposit-start / funnel-bridge-view`
- Deposit success rate:
  - `funnel-wrtc-deposit-ok / funnel-wrtc-deposit-start`
- Withdraw start rate:
  - `funnel-wrtc-withdraw-start / funnel-bridge-view`

Use the same date window as baseline to compare pre/post movement.
