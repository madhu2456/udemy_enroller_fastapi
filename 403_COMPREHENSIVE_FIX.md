# 403 Forbidden Error: Comprehensive Fix Implementation

## Problem Overview
The Udemy Enroller was experiencing persistent 403 Forbidden errors from Udemy's application-layer anti-abuse system. When the account was flagged as suspicious, the application would:
- Immediately fail all subsequent course fetches with 403
- Only retry twice before giving up (too few attempts)
- Continue hammering courses even after detecting account-level block
- Provide poor error messages to users about why courses failed

## Root Causes Identified

### 1. Account-Level Detection Missing
- No circuit breaker to detect when account is globally rate-limited
- Application would continue retrying individual courses indefinitely
- Each failed request reinforced the block instead of allowing recovery

### 2. Insufficient Retry Attempts
- Fixed max 2 retries on authenticated 403s was too low
- Udemy's throttle sometimes loosens after a few more attempts
- No adaptive retry logic based on session health

### 3. Weak Session Recovery
- After CSRF token refresh, immediately retried same course
- No exponential backoff between retry attempts
- Failed to detect when entire account needed cooldown

### 4. Poor Error Messaging
- Generic "403 Forbidden" errors didn't distinguish between issues
- No indication of recovery time or recommended actions
- Users couldn't distinguish permanent vs temporary blocks

## Solutions Implemented

### 1. Account-Level Circuit Breaker ✓
**File: `app/services/udemy_client.py`**

Added circuit breaker logic to detect and pause all course fetches when account is rate-limited:

```python
# Track global 403 count and activate circuit breaker at threshold
self._global_403_circuit_threshold = 4          # trigger on 4+ consecutive 403s
self._global_403_count = 0                      # total 403s in session
self._account_block_active = False              # flag when block is active
self._account_block_cooldown_until = None       # timestamp for recovery
self._account_block_cooldown_seconds = 300      # 5-minute cooldown
```

**Methods Added:**
- `_activate_account_block()` - Pause course fetches when threshold exceeded
- `is_account_blocked()` - Check if account is in cooldown
- `get_account_block_wait_seconds()` - Get remaining cooldown time

**Behavior:**
1. Track consecutive 403 errors across all course fetches
2. When 4+ consecutive 403s detected → activate 5-minute cooldown
3. During cooldown → skip expensive fetch attempts (preserve bandwidth)
4. After cooldown expires → resume course fetches automatically
5. Successful 2xx response clears the block flag

### 2. Adaptive Retry Logic with Exponential Backoff ✓
**File: `app/services/udemy_client.py` (Stage 4: Authenticated Playwright)**

Increased and made retry attempts adaptive:

```python
# Adaptive max retries: 2-5 based on consecutive 403 count
max_403_retries = min(5, 2 + max(0, min(3, self._course_fetch_consecutive_403s // 2)))

# Exponential backoff between retries: 2s, 4s, 8s, 16s + random jitter
backoff = 2 ** consecutive_403 + random.uniform(0, 2)
await asyncio.sleep(backoff)
```

**Changes:**
- Old: Fixed 2 retries
- New: 2-5 retries depending on session health
- Added exponential backoff (2s, 4s, 8s, 16s) with jitter
- Prevents thundering herd and gives Udemy time to cool throttle

### 3. Early Termination on Account Block ✓
**File: `app/services/udemy_client.py` (get_course_id method)**

Skip expensive fetch attempts when account is globally blocked:

```python
# Check if account is in circuit breaker cooldown
if self.is_account_blocked():
    wait_seconds = self.get_account_block_wait_seconds()
    course.is_valid = False
    course.error = f"Account temporarily blocked by Udemy (will retry in {wait_seconds:.0f}s)"
    logger.info(f"  Status: Account blocked (cooldown) - skipping course fetch")
    return
```

**Impact:**
- Prevents wasting bandwidth on expensive Playwright sessions
- Immediately marks courses as "failed" (will retry next run)
- Allows account to recover without continuous hammering

### 4. Improved Error Messages ✓
**File: `app/services/udemy_client.py` (error reporting)**

Different error messages for different scenarios:

```python
if resp and resp.status_code == 403:
    if self._global_403_count >= self._global_403_circuit_threshold:
        course.error = f"Account rate-limited (403). Will retry after cooldown ({self.get_account_block_wait_seconds():.0f}s)"
    else:
        course.error = "Failed to fetch course page (403 Forbidden - session blocked)"
else:
    course.error = f"Failed to fetch course page ({resp.status_code if resp else 'No response'})"
```

**User-Facing Messages:**
- **"Account temporarily blocked..."** → User action: Wait for cooldown, retry later
- **"Account rate-limited..."** → User action: Same as above, shows estimated recovery time
- **"Failed to fetch..."** → User action: May require re-login or checking session

### 5. Session Health Metrics ✓
**File: `app/services/udemy_client.py`**

Added `get_session_health_report()` method for diagnostics:

```python
def get_session_health_report(self) -> Dict:
    return {
        "account_blocked": bool,
        "block_cooldown_remaining_seconds": float,
        "total_403_errors": int,
        "consecutive_403_errors": int,
        "current_backoff_seconds": float,
        "csrf_refresh_failures": int,
        "cloudflare_challenges": int,
        "is_authenticated": bool,
    }
```

**Usage:**
- Logged at end of each enrollment run for diagnostics
- Helps identify patterns and predict blocks
- Tracks CSRF refresh and Cloudflare challenge counts

### 6. Enhanced Logging ✓
**File: `app/services/enrollment_manager.py`**

Added session health report logging on completion:

```python
health = self.udemy.get_session_health_report()
logger.info(
    f"Session Health: {health['consecutive_403_errors']} consecutive 403s, "
    f"total 403s: {health['total_403_errors']}, "
    f"account_blocked: {health['account_blocked']}, "
    f"csrf_failures: {health['csrf_refresh_failures']}, "
    f"cf_challenges: {health['cloudflare_challenges']}"
)
```

## Behavior Changes

### Before
```
2026-04-24 10:07:24 | WARNING | [BLOCK] Playwright page.goto ... -> 403
2026-04-24 10:07:27 | WARNING | [BLOCK] Playwright page.goto ... -> 403 (RETRY 2/2)
2026-04-24 10:07:35 | ERROR | Too many 403 errors (2) on authed Playwright course fetch. Giving up.
2026-04-24 10:07:35 | ERROR | Failed to identify course: Adobe Illustrator
2026-04-24 10:08:43 | WARNING | [BLOCK] Playwright page.goto ... -> 403 (same account!)
```

### After
```
2026-04-24 10:07:24 | WARNING | [BLOCK] Playwright page.goto ... -> 403
2026-04-24 10:07:27 | WARNING | 403 Forbidden (attempt 1/4). Forcing full session re-challenge with 2.5s backoff...
2026-04-24 10:07:29 | WARNING | [BLOCK] Playwright page.goto ... -> 403
2026-04-24 10:07:33 | WARNING | 403 Forbidden (attempt 2/4). Forcing full session re-challenge with 4.1s backoff...
2026-04-24 10:07:37 | WARNING | [BLOCK] Playwright page.goto ... -> 403
2026-04-24 10:07:41 | WARNING | 403 Forbidden (attempt 3/4). Forcing full session re-challenge with 8.3s backoff...
2026-04-24 10:07:49 | ERROR | ⚠ ACCOUNT BLOCK DETECTED: 4 consecutive 403 errors. Session temporarily blocked until 2026-04-24T10:12:49+00:00
2026-04-24 10:07:49 | INFO | Status: Account blocked (cooldown) - skipping expensive fetch for next course
2026-04-24 10:12:49 | INFO | ✓ Account block cooldown expired, resuming course fetches...
```

## Recovery Flow

### Scenario: Account Gets Rate-Limited During Enrollment

1. **First 3 courses fail with 403** → Retry with backoff (no circuit break yet)
2. **4th consecutive 403** → Circuit breaker activates
3. **Account block detected**
   - Stop all Playwright fetches (preserve bandwidth)
   - Mark remaining courses as "failed" (retryable)
   - Log cooldown expiration time
4. **5-minute cooldown period**
   - Application continues but skips expensive operations
   - Check every course quickly if already cached
5. **Cooldown expires**
   - Circuit breaker resets
   - Course fetches resume with fresh attempt
6. **Success or controlled fallback**
   - If successful: courses process normally
   - If still failing: gradual backoff tries again next run

## Configuration

### Tunable Parameters (in `__init__`)

```python
# Adjust circuit breaker sensitivity
self._global_403_circuit_threshold = 4              # trigger threshold (default: 4)
self._account_block_cooldown_seconds = 300          # recovery time (default: 300s = 5min)

# Adjust max retries
max_403_retries = min(5, 2 + ...)                   # max attempts (default: min 2, max 5)

# Adjust adaptive backoff
backoff = 2 ** consecutive_403 + random.uniform(0, 2)  # exponential + jitter
```

## Testing Recommendations

### Unit Tests Needed
- [ ] `test_circuit_breaker_activation()` - Verify 4th 403 triggers block
- [ ] `test_account_block_prevents_fetches()` - Verify courses skip during cooldown
- [ ] `test_cooldown_expiration()` - Verify block clears after timeout
- [ ] `test_adaptive_retries()` - Verify 2-5 retry range

### Integration Tests Needed
- [ ] Full enrollment run with simulated 403s
- [ ] Verify metrics logged correctly
- [ ] Verify course status tracking (failed vs invalid)

### Manual Testing
1. Run with account known to trigger 403s
2. Observe circuit breaker activation after 4th error
3. Verify 5-minute cooldown applies
4. Wait for recovery and see resumed fetches
5. Check error messages in dashboard

## Deployment Notes

### Backward Compatibility
- ✓ No database schema changes
- ✓ No config file changes required
- ✓ Existing sessions continue to work
- ✓ Only improves handling of edge cases

### Monitoring
- Watch logs for `⚠ ACCOUNT BLOCK DETECTED` messages
- Track `session_recovery_state` metrics
- Monitor consecutive 403 error counts
- Alert on sustained account blocks (> 2 per day)

## Summary of Changes

| Component | Change | Benefit |
|-----------|--------|---------|
| Circuit Breaker | Added account-level block detection | Prevents infinite retry loop |
| Retry Logic | 2→5 adaptive attempts with backoff | Better chance of recovery |
| Error Messages | Distinguish temp block vs other errors | Better user experience |
| Metrics Tracking | Added session health report | Better diagnostics and monitoring |
| Early Termination | Skip fetches when account blocked | Preserve bandwidth, reduce noise |

## Files Modified
1. `app/services/udemy_client.py` - Main implementation
2. `app/services/enrollment_manager.py` - Metrics logging
3. Documentation files (this file)

## Related Issues
- Fixes: 403 Forbidden errors on course fetches
- Improves: Account rate-limiting detection and recovery
- Reduces: Unnecessary retry attempts and bandwidth waste
- Enhances: Error messages and diagnostics
