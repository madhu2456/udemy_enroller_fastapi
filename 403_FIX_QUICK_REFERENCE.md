# 403 Error Fix - Quick Reference

## What Was Fixed

### 🚨 Problem
- Udemy was returning 403 Forbidden errors on course fetches
- Application would retry only 2 times then give up
- Account would get globally blocked but app would keep hammering
- Poor error messages left users confused

### ✅ Solutions Implemented

| Issue | Fix | Benefit |
|-------|-----|---------|
| Only 2 retries | Increased to 2-5 adaptive retries | Better recovery chance |
| No circuit breaker | Added account-level block detection | Prevents infinite retry loop |
| No backoff between retries | Added exponential backoff (2s, 4s, 8s, 16s) | Gives Udemy time to recover |
| Poor error messages | Added context-specific messages | Users know what happened and when to retry |
| No metrics | Added session health report | Better diagnostics |

## New Features

### Circuit Breaker
When 4+ consecutive 403 errors are detected:
1. Account is marked as temporarily blocked
2. Course fetches are paused for 5 minutes
3. Remaining courses are marked "failed" (retryable next run)
4. Logs show: `⚠ ACCOUNT BLOCK DETECTED`

### Adaptive Retries
- 2-5 attempts depending on session health
- Exponential backoff: 2s → 4s → 8s → 16s (+ random jitter)
- Each retry attempts CSRF refresh
- Log shows: `403 Forbidden (attempt 1/4)`

### Better Error Messages
- **"Account temporarily blocked..."** → Wait 5 minutes, try later
- **"Account rate-limited..."** → Shows estimated recovery time
- **"Failed to fetch..."** → Indicates why (403, network, etc.)

### Session Health Metrics
Logged at end of each run:
```
Session Health: 2 consecutive 403s, total 403s: 5, account_blocked: false,
csrf_failures: 0, cf_challenges: 1
```

## Recovery Behavior

### During Account Block (5-minute cooldown)
- ✗ No course fetches attempted (preserve bandwidth)
- ✗ Playwright pages not opened
- ✗ CSRF refreshes not forced
- ✓ Courses marked "failed" → retried next run
- ✓ Circuit breaker prevents thundering herd

### After Cooldown Expires
- ✓ Circuit breaker resets
- ✓ Course fetches resume
- ✓ Adaptive retries apply
- ✓ Each course gets 2-5 chances

## How to Monitor

### Logs to Watch For
```
⚠ ACCOUNT BLOCK DETECTED: 4 consecutive 403 errors
✓ Account block cooldown expired, resuming course fetches...
403 Forbidden (attempt 1/4). Forcing full session re-challenge with 2.5s backoff
```

### Metrics to Check
In enrollment run completion log:
- `consecutive_403_errors` - Current streak (should reset on success)
- `total_403_errors` - Total in this session
- `account_blocked` - Is circuit breaker active?
- `csrf_failures` - Token refresh issues
- `cf_challenges` - Cloudflare challenges faced

## Configuration (if needed)

**File:** `app/services/udemy_client.py` lines 95-107

```python
self._global_403_circuit_threshold = 4              # Trigger at N errors
self._account_block_cooldown_seconds = 300          # Recovery wait (5 min)
max_403_retries = min(5, 2 + ...)                   # Max attempts (2-5)
```

## Testing the Fix

### Simulate 403 Errors
1. Temporarily block course URLs in your network
2. Start enrollment run
3. Observe circuit breaker activation after 4 errors
4. Verify 5-minute pause
5. Check logs for recovery messages

### Verify Metrics
1. Run enrollment
2. Check final log for session health report
3. Confirm metrics match expected values

## Deployment
- ✓ No database changes needed
- ✓ No config changes required
- ✓ Backward compatible
- ✓ Automatic rollback on error (uses existing session)

## Next Steps
- Monitor production logs for `ACCOUNT BLOCK DETECTED`
- Alert on sustained blocks (>2 per day = possible issue)
- Adjust cooldown time if needed (currently 300s = 5 min)
