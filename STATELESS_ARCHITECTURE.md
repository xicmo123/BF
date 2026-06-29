# Stateless Auto-Rollout Architecture

## Overview

The auto-rollout system has been refactored from a stateful background thread model to a **stateless, externally-triggered model**. This allows the system to be deployed in containerized/serverless environments and controlled via standard scheduling tools (Cronjob, Kubernetes CronJob, external workers, etc.).

## Architecture Changes

### Before (Stateful)
- `OpsManager.start_auto_rollout()`: Launches a background `threading.Thread` that runs indefinitely
- `OpsManager.stop_auto_rollout()`: Stops the background thread
- API controls lifecycle: `/rollout/auto/enable` and `/rollout/auto/disable` start/stop threads
- State stored in memory (`_auto_thread`, `_auto_stop_event`)

### After (Stateless)
- ✅ **No background threads** - All threading imports removed from `ops.py`
- ✅ **No lifecycle methods** - `start_auto_rollout()` and `stop_auto_rollout()` deleted
- ✅ **Single evaluation method** - `ops.run_auto_rollout()` performs one complete cycle
- ✅ **External scheduler control** - Cronjob, Kubernetes, or custom scheduler triggers evaluation
- ✅ **Settings flag** - `auto_enabled` boolean in database controls whether external triggers should execute

## Components

### 1. OpsManager.run_auto_rollout()

**Completely stateless evaluation function:**

```python
def run_auto_rollout(self, cycles_stable: int = 5) -> dict[str, Any]:
    """
    Evaluate metrics and adjust rollout one step up/down.
    
    Flow:
    1. Read current rollout state from DB
    2. Read metrics from last N cycles
    3. Compute failure_rate and variance
    4. Apply upgrade/downgrade rules
    5. Write new state and history to DB
    6. Return result dict
    """
```

**Rules:**
- **Downgrade**: If failure_rate > 5% OR kill_switch enabled → step down one stage or to 0%
- **Upgrade**: If failure_rate < 1% AND variance < 1e-4 AND api_fail == 0 → step up one stage
- **Stages**: [1%, 5%, 10%, 25%]

**Returns**: `{"changed": bool, "to": int, "reason": str}` or `{"error": str}`

### 2. CLI Entrypoint

**File:** `scripts/run_auto_rollout.py`

**Usage:**
```bash
# Run auto-rollout evaluation
python scripts/run_auto_rollout.py

# With options
python scripts/run_auto_rollout.py --cycles-stable 10 --check-enabled

# Check-enabled: Skip if auto_enabled flag is False (safe for Cronjob)
python scripts/run_auto_rollout.py --check-enabled
```

**Output:** JSON result with `status`, `changed`, `to`, `reason` or `error`

**Exit Codes:**
- 0: Success (evaluation completed or skipped due to flag)
- 1: Error

### 3. API Endpoints

#### Webhook: POST /rollout/auto/run
```bash
curl -X POST http://localhost:8000/rollout/auto/run
```

**Behavior:**
- Checks `auto_enabled` flag in database
- If False: Returns `{"skipped": true, "reason": "auto_enabled is False"}` (200)
- If True: Runs evaluation and returns result
- Ideal for: External HTTP-based schedulers

#### Flag Control: POST /rollout/auto/enable
```bash
curl -X POST http://localhost:8000/rollout/auto/enable
```
Sets `auto_enabled = 1` in database. External scheduler will trigger runs.

#### Flag Control: POST /rollout/auto/disable
```bash
curl -X POST http://localhost:8000/rollout/auto/disable
```
Sets `auto_enabled = 0`. External scheduler will skip runs.

## Deployment Patterns

### Pattern 1: Cronjob (Recommended)
```bash
# Run every 60 seconds
* * * * * cd /app && python scripts/run_auto_rollout.py --check-enabled >> /var/log/rollout.log 2>&1

# Or via curl to webhook
* * * * * curl -X POST http://localhost:8000/rollout/auto/run
```

### Pattern 2: Kubernetes CronJob
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: lending-bot-rollout
spec:
  schedule: "*/1 * * * *"  # Every minute
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: rollout
            image: lending-bot:latest
            command: ["python", "scripts/run_auto_rollout.py", "--check-enabled"]
          restartPolicy: OnFailure
```

### Pattern 3: External Worker Service
```python
# Worker service (e.g., Celery, RQ, custom daemon)
import requests
import time

while True:
    try:
        resp = requests.post("http://lending-bot:8000/rollout/auto/run")
        print(f"Rollout result: {resp.json()}")
    except Exception as e:
        print(f"Rollout error: {e}")
    
    time.sleep(60)  # Run every 60 seconds
```

### Pattern 4: CLI Script in Process
```python
# If running in same process as bot
from bitfinex_lending_bot.ops import OpsManager
from bitfinex_lending_bot.storage import SQLiteRepository
from bitfinex_lending_bot.config import load_settings

settings = load_settings()
repo = SQLiteRepository(settings.database_path)
ops = OpsManager(repo, notifier, settings)

# Call whenever needed
result = ops.run_auto_rollout(cycles_stable=5)
print(result)
```

## Database Schema

### rollout_settings Table
```sql
CREATE TABLE rollout_settings (
    id INTEGER PRIMARY KEY,
    auto_enabled INTEGER DEFAULT 1,      -- 0=disabled, 1=enabled
    last_decision TEXT,                  -- "AUTO_UP", "AUTO_DOWN", "AUTO_ENABLED", etc.
    last_reason TEXT,                    -- Human-readable reason
    updated_at TEXT                      -- ISO timestamp
);
```

**Read via API:** `GET /rollout/settings`
```json
{
  "auto_enabled": 1,
  "last_decision": "AUTO_UP",
  "last_reason": "failure_rate=0.02 var=0.000001 api_fail=0",
  "updated_at": "2026-06-29T10:30:45.123456"
}
```

## Testing

### Unit Test: CLI Script
```bash
cd /home/wayne.chiu/bitfinex-lending-bot
python scripts/run_auto_rollout.py --help
python scripts/run_auto_rollout.py
```

### Integration Test: API Webhook
```bash
# Enable auto-rollout
curl -X POST http://localhost:8000/rollout/auto/enable

# Trigger evaluation
curl -X POST http://localhost:8000/rollout/auto/run

# Check result
curl http://localhost:8000/rollout/settings
```

## Benefits

1. **No background threads** - Simpler, safer, easier to debug
2. **Stateless** - No in-memory state loss on restart
3. **Flexible scheduling** - Works with any external scheduler
4. **Containerization-friendly** - No daemon management complexity
5. **Observable** - Each run logs metrics and history to database
6. **Control** - Enable/disable via API flag at runtime
7. **Fault-tolerant** - Each run is independent; failures don't cascade

## Migration Notes

- ✅ Old `start_auto_rollout()` and `stop_auto_rollout()` methods removed
- ✅ No changes to strategy, risk, or execution logic
- ✅ Existing `/rollout/set` and `/rollout/stop` endpoints unchanged
- ✅ All metrics and history persisted to database as before
- ✅ Backward compatible: API endpoints `/rollout/auto/{enable,disable,run}` still available
