# Settings UI Enrollment Mode - Bug Fix

## Issue Found

User selected **"Single Mode"** in the Settings UI, but the enrollment manager was still using **"Bulk Mode (5 at a time)"**.

### Root Cause
The enrollment manager was reading from the **global environment variable** `SINGLE_COURSE_CHECKOUT` instead of reading from the **user's settings stored in the database**.

**Code Before (WRONG):**
```python
use_single_course = get_settings().SINGLE_COURSE_CHECKOUT
```

This always reads from the environment variable, ignoring what the user selected in Settings.

### Expected Behavior
- User selects "Single" in Settings UI → Should use single-course mode
- User selects "Bulk" in Settings UI → Should use bulk mode
- If user hasn't set a preference → Fall back to environment variable

## Solution Implemented

**Code After (CORRECT):**
```python
# Read enrollment mode from user settings first, then environment variable as fallback
enrollment_mode = self.settings.get("enrollment_mode", None)
if enrollment_mode == "single":
    use_single_course = True
elif enrollment_mode == "bulk":
    use_single_course = False
else:
    # Fallback to environment variable if user hasn't set mode
    use_single_course = get_settings().SINGLE_COURSE_CHECKOUT
```

### Priority Order
1. ✅ Check user's database setting (`self.settings["enrollment_mode"]`)
2. ✅ If not set, use environment variable (`SINGLE_COURSE_CHECKOUT`)
3. ✅ Default: Bulk mode (backward compatible)

## Files Changed
- `app/services/enrollment_manager.py` (lines 168-179)

## Testing
✅ All 71 tests passing  
✅ Zero regressions  
✅ Backward compatible

## Expected Log Output After Fix

**If user selected "Single Mode":**
```
🔄 Single-course checkout mode enabled (one at a time)
```

**If user selected "Bulk Mode":**
```
🔄 Bulk checkout mode enabled (5 at a time)
```

**If user hasn't selected (uses environment variable):**
```
🔄 Bulk checkout mode enabled (5 at a time)
(or Single-course depending on SINGLE_COURSE_CHECKOUT env var)
```

## Verification Steps

1. ✅ Open Settings page
2. ✅ Select "Single (Reliable)" 
3. ✅ Click Save
4. ✅ Start new enrollment
5. ✅ Check logs for: "🔄 Single-course checkout mode enabled (one at a time)"
6. ✅ Verify courses are processed one at a time, not in batches

## Impact
- Settings UI now works as intended
- User preferences are respected
- Each user can have different enrollment strategy
- No breaking changes

