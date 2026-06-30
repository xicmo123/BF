# 500 Error Investigation - 2026-06-30

## Summary
Investigated 500 errors occurring on `/v2/auth/r/wallets` endpoint. Found that the actual error is `["error",10100,"apikey: digest invalid"]` - a Bitfinex API signature validation failure, not a generic server error.

## Findings

### 1. Response Body Logging Status
**Status: ✅ Deployed**
- The `response_body=...` logging change was successfully deployed
- Evidence from logs:
  ```
  2026-06-30 05:20:11.811 | ERROR | bitfinex_lending_bot.client:requests_transport:61 - Bitfinex HTTP 500 https://api.bitfinex.com/v2/auth/r/wallets response_body=["error",10100,"apikey: digest invalid"]
  ```

### 2. Complete 500 Error Logs
**Actual Error:** `["error",10100,"apikey: digest invalid"]`

This is a Bitfinex API signature validation error (error code 10100), not a generic 500 Internal Server Error. The error indicates that the API signature digest is invalid.

Sample log entries:
```
2026-06-30 05:20:11.811 | ERROR | bitfinex_lending_bot.client:requests_transport:61 - Bitfinex HTTP 500 https://api.bitfinex.com/v2/auth/r/wallets response_body=["error",10100,"apikey: digest invalid"]
2026-06-30 05:20:11.812 | WARNING | bitfinex_lending_bot.client:_request:175 - Bitfinex server error 500 on /v2/auth/r/wallets attempt=1/3 retrying in 1.0s response_body=["error",10100,"apikey: digest invalid"]
2026-06-30 05:20:13.456 | ERROR | bitfinex_lending_bot.client:requests_transport:61 - Bitfinex HTTP 500 https://api.bitfinex.com/v2/auth/r/wallets response_body=["error",10100,"apikey: digest invalid"]
2026-06-30 05:20:13.457 | WARNING | bitfinex_lending_bot.client:_request:175 - Bitfinex server error 500 on /v2/auth/r/wallets attempt=2/3 retrying in 2.0s response_body=["error",10100,"apikey: digest invalid"]
2026-06-30 05:20:15.715 | ERROR | bitfinex_lending_bot.client:requests_transport:61 - Bitfinex HTTP 500 https://api.bitfinex.com/v2/auth/r/wallets response_body=["error",10100,"apikey: digest invalid"]
```

### 3. Cron Schedule vs Execution Time
**Status: ✅ No Overlap**
- **Schedule:** Systemd timer runs every 5 minutes (`OnCalendar=*:0/5`)
- **Execution Time:** ~9.8 seconds per run (from systemctl status)
- **Conclusion:** No overlap - 5 minutes >> 10 seconds

### 4. Multiple Processes Using Same API Key
**Status: ✅ No Conflicts Found**

Running processes:
- `bfx-dashboard.service` (uvicorn dashboard API) - **Does NOT make Bitfinex API calls**, only reads from database
- `bfx-bot.service` (runs via systemd timer) - **Only process making Bitfinex API calls**

No auto_rollout cron job found. No evidence of multiple processes simultaneously using the same API key.

### 5. Nonce Factory Implementation
**Status: ✅ Thread-safe within single process**

Implementation in `src/bitfinex_lending_bot/client.py`:
```python
_nonce_lock = threading.Lock()
_last_nonce: int = 0

def _monotonic_nonce() -> str:
    global _last_nonce
    with _nonce_lock:
        candidate = int(time.time() * 1_000_000)
        _last_nonce = max(_last_nonce + 1, candidate)
        return str(_last_nonce)
```

- Uses threading.Lock() for thread safety
- Uses microsecond timestamp (`time.time() * 1_000_000`)
- Implements monotonic increment: `max(_last_nonce + 1, candidate)`
- **Conclusion:** Should prevent nonce conflicts within a single process

## Root Cause Analysis

The error `["error",10100,"apikey: digest invalid"]` indicates a signature validation failure, not a nonce issue. Possible causes:

1. **API key/secret mismatch** - The stored credentials may not match what Bitfinex expects
2. **Clock skew** - System clock may be out of sync, causing signature validation to fail
3. **Credential corruption** - Encrypted API secret may have been corrupted during storage/retrieval
4. **Bitfinex API changes** - Bitfinex may have changed their signature validation logic

## Recommendations

1. **Verify API credentials** - Re-enter the API key and secret through the dashboard
2. **Check system clock** - Ensure system time is synchronized (run `timedatectl status`)
3. **Monitor for recurrence** - Continue monitoring logs for this error pattern
4. **Consider adding clock sync check** - Add a startup check to verify system clock is synchronized

## Next Steps

- Monitor logs for recurrence of the 10100 error
- If error persists, consider re-entering API credentials through the dashboard
- Check system clock synchronization
