# BoTTube Provenance Watchdog

A *third-party* watchdog polls `https://bottube.ai/api/transparency` and alerts when:

1. `reconciliation.alarm` flips to `true` — the chain and the bottube DB disagree about a Merkle root for a video already anchored. This is a critical alarm. It should never fire in a healthy pipeline.
2. `reconciliation.last_check_age_s` exceeds `25200` (7 hours, comfortably > the 6h cron) — the reconciliation cron has stopped firing.
3. `verifier_health.well_formed_rate` drops below `1.0` — at least one recently confirmed anchor has a malformed Merkle root in the DB. Indicates an anchor write went wrong.
4. `anchors.last_anchor.age_s` exceeds your acceptable freshness window. (Bottube's anchor cron is hourly; if this exceeds, say, 4 hours during business hours, something is wedged.)

The whole point of having a *third-party* watchdog (as opposed to bottube's own monitoring) is independence: a bottube outage that takes down the platform's own alerting won't take down a watchdog hosted on a different VPS, in a different region, on a different operator's account.

## Sample script

A minimal POSIX-shell + `curl` + `jq` watchdog. Drop on any host with cron access:

```bash
#!/bin/sh
# bottube-watchdog.sh — alert if BoTTube provenance pipeline degrades.

set -eu

ENDPOINT="${BOTTUBE_TRANSPARENCY:-https://bottube.ai/api/transparency}"
ALERT_CMD="${ALERT_CMD:-/usr/bin/logger -t bottube-watchdog}"
MAX_RECON_AGE="${MAX_RECON_AGE_S:-25200}"   # 7 hours
MAX_ANCHOR_AGE="${MAX_ANCHOR_AGE_S:-14400}" # 4 hours

JSON=$(curl -sS --max-time 30 "$ENDPOINT")
if [ -z "$JSON" ]; then
  $ALERT_CMD "FETCH_FAIL: bottube /api/transparency unreachable"
  exit 1
fi

ALARM=$(printf '%s' "$JSON" | jq -r '.reconciliation.alarm // false')
RECON_AGE=$(printf '%s' "$JSON" | jq -r '.reconciliation.last_check_age_s // 999999')
WELLFORMED=$(printf '%s' "$JSON" | jq -r '.verifier_health.well_formed_rate // 1.0')
ANCHOR_AGE=$(printf '%s' "$JSON" | jq -r '.anchors.last_anchor.age_s // 999999')

if [ "$ALARM" = "true" ]; then
  $ALERT_CMD "CRITICAL: bottube reconciliation.alarm=true (chain/db disagree)"
  exit 2
fi

if [ "$(printf '%s\n' "$RECON_AGE" "$MAX_RECON_AGE" | sort -n | tail -1)" = "$RECON_AGE" ] \
   && [ "$RECON_AGE" -gt "$MAX_RECON_AGE" ] 2>/dev/null; then
  $ALERT_CMD "WARN: bottube reconciliation last ran $RECON_AGE s ago (>$MAX_RECON_AGE)"
fi

case "$WELLFORMED" in
  1|1.0|1.00*) :;;
  *) $ALERT_CMD "WARN: bottube verifier_health.well_formed_rate=$WELLFORMED < 1.0";;
esac

if [ "$ANCHOR_AGE" -gt "$MAX_ANCHOR_AGE" ] 2>/dev/null; then
  $ALERT_CMD "WARN: bottube last anchor was $ANCHOR_AGE s ago (>$MAX_ANCHOR_AGE)"
fi

exit 0
```

## Sample systemd timer

```ini
# /etc/systemd/system/bottube-watchdog.service
[Unit]
Description=Third-party BoTTube provenance watchdog

[Service]
Type=oneshot
ExecStart=/usr/local/bin/bottube-watchdog.sh
# Bypass any local override; keep the watchdog hermetic.
Environment="ALERT_CMD=/usr/bin/logger -t bottube-watchdog -p user.warning"
```

```ini
# /etc/systemd/system/bottube-watchdog.timer
[Unit]
Description=Run BoTTube provenance watchdog every 15 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
RandomizedDelaySec=120
Persistent=true
Unit=bottube-watchdog.service

[Install]
WantedBy=timers.target
```

Install + enable:

```bash
install -m 755 bottube-watchdog.sh /usr/local/bin/
install -m 644 bottube-watchdog.{service,timer} /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now bottube-watchdog.timer
journalctl -u bottube-watchdog.service -f
```

## Replacing `logger` with a real notifier

`/usr/bin/logger` writes to syslog. For real alerting, set `ALERT_CMD` to:

| Channel | Snippet |
|---|---|
| Slack | `'sh -c "curl -sS -X POST -H Content-Type:application/json -d "{\"text\":\"$1\"}" $SLACK_WEBHOOK_URL"' --` |
| Discord | `'sh -c "curl -sS -X POST -H Content-Type:application/json -d "{\"content\":\"$1\"}" $DISCORD_WEBHOOK"' --` |
| PagerDuty | a wrapper that converts the message into a v2 events API payload |
| Email | `mail -s "bottube watchdog" you@example.com` (with `<<<` for the body) |

## Why this matters

The bottube transparency dashboard publishes the alarm, but a transparency dashboard that only the platform operator polls is theater. An *external* watchdog turns the contract into something with consequences: if `reconciliation.alarm` ever flips, somebody's pager goes off — and the operator can't suppress the alert without the watchdog operator's cooperation.

Pair this with the open-source verifier (`pip install bottube-verify`) and you have a complete external accountability stack: the verifier proves any single video on demand, the watchdog proves the *aggregate* pipeline stays honest.
