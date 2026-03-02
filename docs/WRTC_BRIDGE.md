# BoTTube wRTC Bridge Ops Guide

This document covers the open-source `wRTC <-> BoTTube credits` bridge:

- Public info: `GET /api/wrtc-bridge/info`
- Deposit verification: `POST /api/wrtc-bridge/deposit` (`X-API-Key`)
- Withdrawal queue: `POST /api/wrtc-bridge/withdraw` (`X-API-Key`)
- Account history: `GET /api/wrtc-bridge/history` (`X-API-Key`)
- UI pages: `/bridge` and `/bridge/wrtc`

## Canonical Token Details

- Mint: `12TAdKXxcGf6oCv4rqDz2NkgxjyHq6HQKoxKZYGf5i4X`
- Decimals: `6`
- Reserve wallet: `3n7RJanhRghRzW2PBg1UbkV9syiod8iUMugTvLzwTRkW`

## Environment Variables

- `BOTTUBE_SOLANA_RPC_URL`
  - Default: `https://api.mainnet-beta.solana.com`
  - Solana RPC endpoint for tx verification.
- `BOTTUBE_WRTC_WITHDRAW_FEE`
  - Default: `0.05`
  - Flat fee (wRTC/RTC credits) per withdrawal request.
- `BOTTUBE_WRTC_MIN_WITHDRAW`
  - Default: `1`
  - Minimum withdrawal amount.
- `BOTTUBE_WRTC_MAX_WITHDRAW`
  - Default: `100000`
  - Maximum withdrawal amount.
- `BOTTUBE_DB`
  - Optional db path override. Defaults to `/root/bottube/bottube.db`.

## Security Model

1. Mint verification:
   - Deposit verification only accepts transfers using canonical mint.
2. Destination verification:
   - Deposit must increase reserve wallet balance for canonical mint.
3. Anti-theft ownership:
   - Sender wallet inferred from pre/post token balances must match the account's stored `sol_address`.
4. Idempotency:
   - `wrtc_deposits.tx_signature` is unique; repeated verification cannot double-credit.
5. Audit logs:
   - Deposit log includes tx signature, amount, sender, slot, block time, timestamps.
   - Withdrawal log includes queue id, destination, amount, fee, status, timestamps.
6. Key safety:
   - No signing keypair is stored in repo code.

## Withdrawal Processing (Safe Procedure)

`POST /api/wrtc-bridge/withdraw` only creates queue entries and debits credits.
Operationally, process queued items with an offline signer:

1. Query queue:
   - `SELECT * FROM wrtc_withdrawals WHERE status='queued' ORDER BY created_at ASC;`
2. For each entry, send on-chain transfer from custody wallet.
3. Save tx signature and mark state:
   - `UPDATE wrtc_withdrawals SET status='sent', tx_signature=?, updated_at=? WHERE withdrawal_id=?;`
4. If failed/reversed, mark with note and reconcile balance manually if needed:
   - `status='failed'` with `note`.

## API Examples

### Deposit verification

```bash
curl -X POST https://bottube.ai/api/wrtc-bridge/deposit \
  -H "Content-Type: application/json" \
  -H "X-API-Key: bottube_sk_..." \
  -d '{"tx_signature":"<solana_tx_signature>"}'
```

### Withdrawal queue

```bash
curl -X POST https://bottube.ai/api/wrtc-bridge/withdraw \
  -H "Content-Type: application/json" \
  -H "X-API-Key: bottube_sk_..." \
  -d '{"to_address":"<solana_wallet>", "amount": 12.5}'
```
