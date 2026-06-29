# Auto-Rollout Usage Guide

## Quick Start

### CLI (Recommended for Cronjob/Kubernetes)

```bash
# Basic execution
python scripts/run_auto_rollout.py

# With check for enabled flag (safe for production Cronjob)
python scripts/run_auto_rollout.py --check-enabled

# Custom cycles stable parameter
python scripts/run_auto_rollout.py --cycles-stable 10
```

### API Webhook

```bash
# Enable auto-rollout
curl -X POST http://localhost:8000/rollout/auto/enable

# Trigger evaluation
curl -X POST http://localhost:8000/rollout/auto/run

# Disable auto-rollout
curl -X POST http://localhost:8000/rollout/auto/disable

# Check status
curl http://localhost:8000/rollout/settings
```

## Setup Examples

### Cronjob Setup

```bash
# Add to crontab
crontab -e

# Run every minute
* * * * * cd /home/wayne.chiu/bitfinex-lending-bot && python scripts/run_auto_rollout.py --check-enabled >> /var/log/rollout.log 2>&1

# Run every 5 minutes
*/5 * * * * cd /home/wayne.chiu/bitfinex-lending-bot && python scripts/run_auto_rollout.py --check-enabled >> /var/log/rollout.log 2>&1
```

### Docker/Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: lending-bot-auto-rollout
  namespace: default
spec:
  schedule: "*/1 * * * *"  # Every minute
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: lending-bot
          containers:
          - name: rollout
            image: lending-bot:latest
            command: ["python", "scripts/run_auto_rollout.py", "--check-enabled"]
            env:
            - name: DATABASE_PATH
              value: /data/lending_bot.sqlite3
            volumeMounts:
            - name: data
              mountPath: /data
          restartPolicy: OnFailure
          volumes:
          - name: data
            persistentVolumeClaim:
              claimName: lending-bot-data
```

### systemd Timer

Create `/etc/systemd/system/lending-bot-rollout.service`:
```ini
[Unit]
Description=Bitfinex Lending Bot Auto-Rollout
After=network.target

[Service]
Type=oneshot
User=lending-bot
WorkingDirectory=/home/wayne.chiu/bitfinex-lending-bot
ExecStart=/usr/bin/python3 scripts/run_auto_rollout.py --check-enabled
StandardOutput=journal
StandardError=journal
```

Create `/etc/systemd/system/lending-bot-rollout.timer`:
```ini
[Unit]
Description=Bitfinex Lending Bot Auto-Rollout Timer
Requires=lending-bot-rollout.service

[Timer]
OnBootSec=2min
OnUnitActiveSec=1min
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:
```bash
sudo systemctl enable lending-bot-rollout.timer
sudo systemctl start lending-bot-rollout.timer
sudo systemctl status lending-bot-rollout.timer
```

## Monitoring

### Check Last Run Result

```bash
curl http://localhost:8000/rollout/settings | jq .
```

Output:
```json
{
  "auto_enabled": 1,
  "last_decision": "AUTO_UP",
  "last_reason": "failure_rate=0.0 var=0.000001 api_fail=0",
  "updated_at": "2026-06-29T10:45:30.123456"
}
```

### View Full History

```bash
curl http://localhost:8000/rollout/state | jq .history
```

### Check Current Rollout State

```bash
curl http://localhost:8000/rollout
```

Output:
```json
{
  "stage": 2,
  "allocation_percent": 5,
  "max_percent": 100,
  "updated_at": "2026-06-29T10:45:30.123456"
}
```

## Production Checklist

- [ ] Set up external scheduler (Cronjob, Kubernetes CronJob, systemd timer)
- [ ] Use `--check-enabled` flag in production
- [ ] Configure logging: Redirect stdout/stderr to log file or system logger
- [ ] Set up monitoring: Alert on `last_decision == "AUTO_DOWN"` or `failure_rate > 0.05`
- [ ] Test failure scenarios: Kill switch, high failure rate, API failures
- [ ] Document runbook: How to manually enable/disable auto-rollout
- [ ] Backup database: Regular backups of SQLite database

## Manual Control

### Disable Auto-Rollout (Emergency)
```bash
curl -X POST http://localhost:8000/rollout/auto/disable
```

### Manual Rollout Adjustment
```bash
# Set to 1%
curl -X POST http://localhost:8000/rollout/set -H "Content-Type: application/json" -d '{"percent": 1}'

# Emergency stop (0%)
curl -X POST http://localhost:8000/rollout/stop -H "Content-Type: application/json" -d '{"reason": "emergency"}'
```

## Troubleshooting

### Script exits with error
```bash
python scripts/run_auto_rollout.py
# Check output for error message and database path
```

### Auto-rollout not triggering
1. Check if `auto_enabled` flag is True:
   ```bash
   curl http://localhost:8000/rollout/settings
   ```
2. Verify scheduler is running:
   ```bash
   # For Cronjob
   sudo tail -f /var/log/syslog | grep CRON
   
   # For systemd timer
   systemctl status lending-bot-rollout.timer
   ```
3. Check logs:
   ```bash
   tail -f /var/log/rollout.log
   ```

### Downgrade loops
If auto-rollout keeps downgrading:
- Check `failure_rate` in `/rollout/settings`
- Review API failure metrics: `curl http://localhost:8000/metrics`
- Temporarily disable: `curl -X POST http://localhost:8000/rollout/auto/disable`
- Investigate and fix underlying issues

## Implementation Details

See [STATELESS_ARCHITECTURE.md](STATELESS_ARCHITECTURE.md) for detailed architecture documentation.
