# Quick Reference: Critical Fixes Applied

## Summary of Changes

### 1. Checkout Retry Logic
**File:** `app/services/udemy_client.py`

#### `_refresh_csrf_stealth()` 
- **Change:** Now returns `bool` instead of being void
- **Behavior:** Returns `True` if CSRF token successfully refreshed, `False` otherwise
- **Impact:** Callers can now verify refresh succeeded before retrying

#### `_checkout_one()` 
- **Limits:** Max 3 attempts, max 2 consecutive 403s
- **Backoff:** None between retry attempts (within 3 tries)
- **Exit:** Fails immediately after max 403s or max attempts
- **Key Logic:**
  ```python
  max_attempts = 3
  max_403_consecutive = 2
  ```

#### `checkout_single()`
- **Limits:** Max 2 retry attempts
- **Validation:** Checks CSRF token exists and is non-empty
- **Exit:** Fails if refresh returns `False`

#### `bulk_checkout()`
- **Limits:** Max `len(courses) + 2` attempts, max 3 consecutive 403s
- **Backoff:** Exponential: `min(2^(attempt//2), 10) + random(0.5, 2.0)` seconds
- **Exit:** Gives up after max 403s or max attempts
- **Key Logic:**
  ```python
  max_bulk_attempts = len(courses) + 2
  max_403_consecutive = 3
  backoff_delay = min(2 ** (attempt // 2), 10) + random.uniform(0.5, 2.0)
  ```

### 2. HTTP Client Changes
**File:** `app/services/http_client.py`

#### `get()` and `post()`
- **New Parameter:** `retry_403` (default: `False`)
- **Behavior:** 403 errors only retry if explicitly requested with `retry_403=True`
- **Usage in Checkout:**
  ```python
  # Checkout calls now use:
  await self.http.post(..., attempts=1, raise_for_status=False)
  # This prevents HTTP client from auto-retrying 403s
  ```

## Error Handling Flow

### Before (Broken)
```
Request → 403 → Refresh CSRF → Continue → Same request → 403 → Loop forever
```

### After (Fixed)
```
Request → 403 → Count (1) → Refresh CSRF → Check success?
  ├─ Yes → Get new token → Retry (attempt 2)
  ├─ No → Return False immediately
  └─ If count >= 3 → Return False immediately
```

## Logging Improvements

New log messages to track retry behavior:
- `"Stealth: Executing checkout for X via Playwright (attempt N/Max)..."`
- `"Waiting {delay:.1f}s before bulk checkout retry (attempt N/Max)..."`
- `"403 Forbidden... (attempt N/Max). Refreshing session..."`
- `"Too many 403 errors (N). Session may be blocked. Giving up."`
- `"Failed to refresh CSRF token. Session may be invalid."`

## Testing the Fixes

Run tests to verify:
```bash
python -m pytest tests/ -v
```

All 71 tests should pass (1 pre-existing failure unrelated to checkout logic).

## Deployment Notes

1. ✅ No database migrations needed
2. ✅ No new dependencies added
3. ✅ Backward compatible with existing code
4. ✅ Can be deployed as-is with no configuration changes

## Monitoring

After deployment, watch logs for:
- ❌ `"Too many 403 errors"` - Session blocking detected
- ⚠️ `"Failed to refresh CSRF"` - Authentication issues
- ✅ `"Bulk checkout succeeded"` - Successful enrollments
- 🔄 `"Waiting X.Xs before"` - Backoff in action (normal)
