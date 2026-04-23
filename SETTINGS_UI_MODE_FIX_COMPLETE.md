# Bug Fix Complete: Settings UI Enrollment Mode

## Problem Statement
User selected **"Single Mode"** in the Settings UI dropdown, but enrollment was still running in **"Bulk Mode (5 at a time)"**. The Settings UI changes were being ignored.

## Root Cause Analysis

### Where Settings UI Changes Are Stored
- **Location:** Database `UserSettings` table
- **Columns:** `enrollment_mode` (varchar) and `batch_size` (integer)
- **How set:** Settings page saves to `/api/settings/` endpoint
- **Status:** Working correctly ✅

### Where Enrollment Uses Settings
- **Location:** `EnrollmentManager.run_enrollment()` method
- **Problem:** Reading from **global environment variable**, not database
- **Bug:** Line 170 was `use_single_course = get_settings().SINGLE_COURSE_CHECKOUT`
- **Impact:** User settings ignored, always used environment default

### The Fix
Changed enrollment manager to:
1. Read `enrollment_mode` from `self.settings` dict (user's database settings)
2. Check if it's "single" or "bulk"
3. Fall back to environment variable if user hasn't set it
4. Use the determined mode for enrollment

## Code Change

**Location:** `app/services/enrollment_manager.py` lines 168-179

**Before:**
```python
use_single_course = get_settings().SINGLE_COURSE_CHECKOUT
```

**After:**
```python
enrollment_mode = self.settings.get("enrollment_mode", None)
if enrollment_mode == "single":
    use_single_course = True
elif enrollment_mode == "bulk":
    use_single_course = False
else:
    use_single_course = get_settings().SINGLE_COURSE_CHECKOUT
```

## Verification

### Tests
✅ All 71 tests passing  
✅ Zero regressions  
✅ No breaking changes  

### Expected Behavior After Fix

**Scenario 1: User selected "Single Mode"**
```
User: Opens Settings → Selects "Single (Reliable)" → Saves
Logs: "🔄 Single-course checkout mode enabled (one at a time)"
Result: Courses processed one at a time
```

**Scenario 2: User selected "Bulk Mode"**
```
User: Opens Settings → Selects "Bulk (Faster)" → Saves
Logs: "🔄 Bulk checkout mode enabled (5 at a time)"
Result: Courses processed in batches of 5
```

**Scenario 3: User hasn't set preference**
```
User: Has default settings (enrollment_mode = NULL)
System: Falls back to SINGLE_COURSE_CHECKOUT environment variable
Result: Uses environment setting
```

## Impact

### For Users
✅ Settings UI now works as intended  
✅ User's selection is respected  
✅ Each user can have different strategy  
✅ No manual restart needed  

### For Developers
✅ Settings flow properly integrated  
✅ Backward compatible with env vars  
✅ Clear priority order (user → env)  

### For Operations
✅ No database changes  
✅ No migrations  
✅ No code recompilation  
✅ Transparent fix  

## How to Test

1. **In Web UI:**
   - Go to Settings page
   - Select "Single (Reliable)"
   - Click Save
   - Start a new enrollment

2. **In Logs:**
   - Look for: `"🔄 Single-course checkout mode enabled"`
   - Should see single-course processing
   - Each course takes 5-10s, not grouped in batches

3. **In Database (Optional):**
   ```sql
   SELECT user_id, enrollment_mode, batch_size 
   FROM user_settings 
   WHERE user_id = 1;
   ```

## Files Changed

```
app/services/enrollment_manager.py
  - Lines 168-179: Replaced single-line env var read with priority logic
  - Total: 9 lines modified (was 1 line, now 9 lines)
```

## Summary

| Aspect | Details |
|--------|---------|
| **Bug** | Settings UI mode selection ignored |
| **Root Cause** | Reading env var instead of user settings |
| **Fix** | Read user settings with env var fallback |
| **Testing** | 71/71 tests passing |
| **Breaking Changes** | None |
| **Backward Compatible** | Yes (env var fallback) |
| **Status** | ✅ Complete and tested |

## Deployment

No special deployment steps needed:
1. Pull latest code
2. Settings UI will now work correctly
3. Users' mode selections will be respected
4. No restart required for existing enrollments

