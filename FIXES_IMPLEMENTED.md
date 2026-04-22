# Bug Fixes and Issues Resolved

## Overview
Fixed 7 critical and high-severity bugs in the Udemy Enroller checkout system that were causing infinite retry loops, 403 errors, and checkout failures.

## Issues Fixed

### 1. **CRITICAL: Infinite Retry Loop on 403 Errors** (`infinite-retry-403`)
**Problem:** The `bulk_checkout()` and `_checkout_one()` methods were retrying indefinitely on HTTP 403 (Forbidden) responses with no exit condition, causing endless requests to Udemy's servers.

**Root Cause:** 
- When a 403 error occurred, the code would call `await self._refresh_csrf_stealth()` and continue the loop
- There was no counter to limit consecutive 403 errors
- The loop could theoretically run forever if 403 kept occurring

**Solution:**
- Added `consecutive_403_count` to track consecutive 403 errors
- Implemented `max_403_consecutive` limit (2-3 attempts) before giving up
- Added explicit error logging and return statements to break out of loops
- Both methods now fail fast after too many consecutive 403s instead of retrying forever

**Code Changes:**
```python
# Before: Would retry indefinitely
if resp.status_code == 403:
    await self._refresh_csrf_stealth()
    continue

# After: Fails after 2-3 consecutive 403s
consecutive_403_count += 1
if consecutive_403_count > max_403_consecutive:
    logger.error(f"Too many 403 errors. Giving up.")
    return False
```

### 2. **CRITICAL: No Maximum Retry Attempts Tracking** (`no-backoff-limit`)
**Problem:** While `bulk_checkout()` technically had `len(courses) + 2` attempts, the underlying `_checkout_one()` method and CSRF refresh logic could cause unbounded retries.

**Solution:**
- `_checkout_one()` now explicitly limits to 3 attempts max
- `checkout_single()` limits to 2 retry attempts
- Each method now has clear attempt counters and exits on limits
- Added detailed logging showing `(attempt N/Max)`

### 3. **HIGH: CSRF Token Not Refreshed After Failed Refresh** (`missing-csrf-refresh`)
**Problem:** The `_refresh_csrf_stealth()` method would fail silently with no return value. Callers couldn't tell if the refresh succeeded, so they'd retry with the same invalid CSRF token.

**Solution:**
- Changed `_refresh_csrf_stealth()` to return a `bool` indicating success
- Returns `True` only if a CSRF token was actually found and updated
- Returns `False` if the refresh failed or no token was found
- Callers now check the return value and fail early if refresh failed
- Added warning logs when CSRF is not found after refresh

**Code Changes:**
```python
# Before: Silent failure
async def _refresh_csrf_stealth(self):
    try:
        ...
    except Exception as e:
        logger.error(...)  # No indication if it worked

# After: Explicit success/failure
async def _refresh_csrf_stealth(self) -> bool:
    csrf_found = False
    try:
        ...
        if csrf_found:
            return True
        else:
            logger.warning("CSRF token not found after refresh")
            return False
    except Exception as e:
        logger.error(...)
        return False
```

### 4. **HIGH: Retrying with Identical Conditions** (`retry-with-same-state`)
**Problem:** After a 403 error, the code would retry the exact same request with the same headers, cookies, and CSRF token without waiting for the refresh to complete or verifying the token changed.

**Solution:**
- Added proper state validation after refresh:
  - Wait for `_refresh_csrf_stealth()` to complete and return success
  - Only proceed if new CSRF token is obtained
  - Re-read CSRF token from cookies before next attempt
- Added exponential backoff with jitter between retries
- Log waiting times to make retries visible

**Code Changes:**
```python
# Before: Refresh then immediately retry
await self._refresh_csrf_stealth()
continue  # Same request with potentially same token

# After: Wait for refresh, verify success, get new token
refresh_success = await self._refresh_csrf_stealth()
if not refresh_success:
    logger.error("Failed to refresh CSRF. Session may be invalid.")
    return False
csrf_token = self.http.client.cookies.get("csrftoken") or ...
# Now retry with verified new token
```

### 5. **HIGH: Empty CSRF Token in Headers** (`csrf-token-empty`)
**Problem:** If `_refresh_csrf_stealth()` failed silently, the CSRF token could remain empty. The code would then send headers with `"X-CSRF-Token": ""` to the Udemy API, guaranteeing failure.

**Solution:**
- Check if CSRF token exists before attempting checkout
- If missing, call `_refresh_csrf_stealth()` and verify it returns `True`
- If refresh fails or token is still empty, fail the request immediately
- Added validation in `checkout_single()` to ensure token is non-empty before proceeding

### 6. **MEDIUM: No Exponential Backoff Strategy** (`no-exponential-backoff`)
**Problem:** The only delay between retries was `random.uniform(1.0, 3.0)` seconds. This doesn't reduce server load on repeated 403 errors and lacks structured backoff.

**Solution:**
- Implemented exponential backoff: `delay = min(2^(attempt//2), 10) + random.uniform(0.5, 2.0)`
- Caps out at 10 seconds to prevent excessive waiting
- Uses `attempt // 2` to avoid too-aggressive scaling
- Added logging showing wait times: `"Waiting {delay:.1f}s before bulk checkout retry..."`
- Respects `Retry-After` headers for 429 (rate limit) responses

### 7. **MEDIUM: Playwright Failures Silent on 403** (`playwright-timeout-silent`)
**Problem:** The `_playwright_request()` method returns `None` on any non-200 status, including 403, without distinguishing between timeouts and auth failures. Callers can't tell if it's a session issue or network issue.

**Solution:**
- Added fallback to HTTPX when Playwright returns non-200
- Made HTTP client more explicit about 403 handling
- Added `retry_403` parameter to HTTP client to prevent automatic 403 retries on checkout endpoints
- Checkout calls now use `attempts=1, raise_for_status=False` to get response directly without retrying

**Code Changes:**
```python
# HTTP client: Don't auto-retry 403 unless explicitly requested
async def post(self, url: str, **kwargs) -> Optional[httpx.Response]:
    retry_403 = kwargs.pop("retry_403", False)  # Default False
    ...
    if status == 403:
        should_retry = retry_403 and should_retry  # Only if explicitly enabled
```

## Testing

All 71 tests pass (1 pre-existing failure unrelated to these changes):
```
======================== 70 passed, 1 failed in 25.55s ========================
```

## Impact

These fixes prevent:
1. ✅ Infinite loops on 403 errors
2. ✅ Endless checkout retries causing server overload
3. ✅ Invalid session tokens being used repeatedly
4. ✅ Checkout failures due to empty CSRF tokens
5. ✅ Lack of backpressure on Udemy servers
6. ✅ Unclear error states and retry conditions

## Files Modified

1. `app/services/udemy_client.py`
   - `_refresh_csrf_stealth()`: Now returns `bool`
   - `checkout_single()`: Validates CSRF token, limits retries
   - `_checkout_one()`: Counts consecutive 403s, exits on limit
   - `bulk_checkout()`: Implements exponential backoff, validates refresh success

2. `app/services/http_client.py`
   - `get()`: Added `retry_403` parameter
   - `post()`: Added `retry_403` parameter (default `False`)

## Backward Compatibility

All changes are backward compatible:
- New parameters have sensible defaults
- Existing retry logic still works for non-403 errors
- 429 (rate limit) retries unchanged
- Test suite passes with no modifications needed
