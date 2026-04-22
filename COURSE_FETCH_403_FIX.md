# Course Fetch 403 Error Fix

## Issue
When fetching course pages to extract course IDs, the system was receiving 403 Forbidden errors and immediately failing without retry logic. This caused many courses to be marked as invalid with the error message:
```
Status: Invalid - Failed to fetch course page (403)
```

## Root Cause
The `get_course_id()` method in `UdemyClient` had three sequential fallback strategies:
1. **Firecrawl** - Extract course ID via Firecrawl API
2. **Playwright** - Fetch page via Playwright browser
3. **Standard HTTP** - Fetch page via standard HTTPX client

However, when Playwright or HTTP requests returned a **403 Forbidden** status, the code immediately failed without attempting any retry or session refresh. This is problematic because:
- Udemy's anti-bot protections occasionally block requests
- Session tokens may expire temporarily
- A simple CSRF token refresh often resolves the issue

In contrast, the `_checkout_one()` and `bulk_checkout()` methods **did have** retry logic with consecutive 403 tracking and CSRF token refresh, but this logic was missing from course fetching.

## Solution Implemented

Added **retry logic with consecutive 403 tracking** to both Playwright and HTTP fallback paths in `get_course_id()`:

### Key Changes

**File: `app/services/udemy_client.py`**

1. **Playwright Fallback Path** (lines 537-572):
   - Tracks consecutive 403 errors
   - Max 2 consecutive 403 attempts before falling back to standard HTTP
   - On 403: Calls `_refresh_csrf_stealth()` to refresh session
   - Waits 1 second before retry
   - Only marks as failed if max retries exceeded

2. **Standard HTTP Fallback Path** (lines 574-608):
   - Tracks consecutive 403 errors  
   - Max 2 consecutive 403 attempts before giving up
   - On 403: Calls `_refresh_csrf_stealth()` to refresh session
   - Waits 1 second before retry
   - Marks course as invalid only after all retries exhausted

3. **Test Updates** (file: `tests/test_udemy_client_extraction.py`):
   - Updated `test_get_course_id_success_with_metadata` to mock `_playwright_request`
   - Updated `test_get_course_id_fallback_to_extraction` to mock `_playwright_request`
   - Updated `test_get_course_id_not_found` to properly simulate 403 retry behavior

## Behavior Comparison

### Before Fix
```
Course: "AI Recruitment: Automatizace..."
1. Firecrawl: No ID found, try next
2. Playwright: 403 Forbidden → FAIL immediately
   Status: Invalid - Failed to fetch course page (403)
```

### After Fix
```
Course: "AI Recruitment: Automatizace..."
1. Firecrawl: No ID found, try next
2. Playwright: 403 Forbidden
   → Refresh CSRF token via _refresh_csrf_stealth()
   → Wait 1 second
   → Retry Playwright: 403 again
   → Max consecutive (2) reached, fall back to standard
3. Standard HTTP: 403 Forbidden
   → Refresh CSRF token via _refresh_csrf_stealth()
   → Wait 1 second
   → Retry HTTP: Success (200)
   → Extract course ID from response
   Status: Valid/Added to batch/Expired (based on coupon)
```

## Technical Details

### Max Consecutive 403 Limits
- Playwright: **2 consecutive 403s before fallback to HTTP**
- Standard HTTP: **2 consecutive 403s before giving up**
- Rationale: 2-3 attempts is sufficient to distinguish temporary blocks from persistent ones

### CSRF Refresh Mechanism
Uses the existing `_refresh_csrf_stealth()` method which:
1. Opens Playwright browser to Udemy home page
2. Detects Cloudflare challenges and waits
3. Extracts new CSRF token via multiple methods (cookies, HTML, script data)
4. Updates session cookies in HTTP client

### Logging
Added clear logging to track retry behavior:
- `403 Forbidden on course fetch for [course]. Refreshing session (attempt X/Y)...`
- `Too many 403 errors (X) on Playwright course fetch. Falling back to standard.`
- `Too many 403 errors (X) on standard course fetch. Giving up.`

## Testing

All 71 tests pass including:
- ✅ Extraction tests for various ID location methods
- ✅ Metadata parsing tests
- ✅ Fallback chain tests with mocked responses
- ✅ Core functionality tests
- ✅ Security validation tests

## Impact

### Courses Now Successfully Processed
The fix enables courses that previously failed with 403 errors to be properly evaluated:
- ✅ Course ID extracted successfully
- ✅ Coupon status determined (100% off, partial, expired, or none)
- ✅ Proper categorization: Valid/Invalid/Expired/No Coupon

### Performance
- Minimal impact: Only adds retries when 403 occurs (rare case)
- In normal operation: Single request succeeds immediately
- With 403 blocks: 2 retries × 1 second wait = ~2 seconds additional per course

### Graceful Degradation
- If Playwright fails: Falls back to standard HTTP
- If both fail: Marks course as invalid with clear error message
- Session refresh prevents infinite loops (max 2 consecutive 403s per method)

## Files Modified
1. `app/services/udemy_client.py` - Added retry logic to `get_course_id()` method
2. `tests/test_udemy_client_extraction.py` - Updated tests to mock Playwright requests

## Backward Compatibility
✅ **Fully backward compatible**
- No changes to method signatures
- No new dependencies
- All existing tests pass
- Retry logic only activates on 403 errors (previously would just fail)

## Future Enhancements
1. Consider **exponential backoff** instead of fixed 1-second delay for retries
2. **Circuit breaker pattern**: Stop retrying if >N consecutive 403s on a single course
3. **Proactive CSRF refresh**: Refresh CSRF token before course fetching (prevent 403s rather than retry after)
4. **Per-scraper retry metrics**: Track which scrapers cause more 403s to identify blocked sources earlier
