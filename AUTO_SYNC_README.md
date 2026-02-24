# BoTTube Auto-Sync (YouTube/TikTok/Instagram)

This worker polls recent BoTTube uploads and schedules cross-platform sync jobs.

## Files
- `auto_sync_daemon.py`
- `auto_sync_config.example.json`

## Run once
```bash
python3 auto_sync_daemon.py --config auto_sync_config.example.json --once
```

## Run continuously
```bash
python3 auto_sync_daemon.py --config auto_sync_config.example.json
```

## Notes
- Default is `dry_run: true` for safe rollout.
- Per-video opt-out via `#nosync` in description.
- Output report: `auto_sync_report.json`.
- OAuth fields are scaffolded for each platform and can be wired to real upload APIs.
