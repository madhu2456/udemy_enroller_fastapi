# Single-Course Checkout Mode

## Overview

Added new **SINGLE_COURSE_CHECKOUT** configuration option to process courses one at a time instead of in bulk batches. This improves reliability by preventing cascading failures when one course fails.

---

## Configuration

### Environment Variable
Set in `.env` or as an environment variable:

```bash
# Default (False = Bulk checkout)
SINGLE_COURSE_CHECKOUT=False

# Enable single-course mode
SINGLE_COURSE_CHECKOUT=True
```

### Python Settings
The setting is available in `config/settings.py`:

```python
SINGLE_COURSE_CHECKOUT: bool = False  # True = one at a time, False = bulk (5 at once)
```

---

## How It Works

### Bulk Mode (Default - SINGLE_COURSE_CHECKOUT=False)
```
Course 1 ─┐
Course 2 ─┼─→ Bulk Checkout (5 courses together) → Results
Course 3 ─┤
Course 4 ─┤
Course 5 ─┘

Process: 5 courses → 1 API call → 1 result
Timing: ~25-40 seconds per batch
Failure: If batch fails, all 5 courses fail
```

### Single-Course Mode (SINGLE_COURSE_CHECKOUT=True)
```
Course 1 → Single Checkout → Result
Course 2 → Single Checkout → Result
Course 3 → Single Checkout → Result
Course 4 → Single Checkout → Result
Course 5 → Single Checkout → Result

Process: 1 course → 1 API call → 1 result
Timing: ~5-10 seconds per course
Failure: If 1 course fails, others continue
```

---

## When to Use Each Mode

### Use Bulk Mode (DEFAULT)
- ✅ Fast processing (5 courses at once)
- ✅ Fewer 403 errors
- ✅ Lower server load
- ✅ Better for reliable IPs

```bash
SINGLE_COURSE_CHECKOUT=False
```

**Recommended for:**
- Localhost/residential IPs
- Free solutions
- Speed is priority

### Use Single-Course Mode
- ✅ Better reliability (no cascading failures)
- ✅ Easier to diagnose problems (per-course granularity)
- ✅ Each course retry independently
- ✅ Better for unstable IPs

```bash
SINGLE_COURSE_CHECKOUT=True
```

**Recommended for:**
- Datacenter IPs (with Firecrawl API key)
- When reliability > speed matters
- Troubleshooting 403 issues

---

## Performance Comparison

| Metric | Bulk Mode | Single-Course |
|--------|-----------|---------------|
| **Speed** | 25-40s per 5 courses | 5-10s per course |
| **Throughput** | 5 courses/batch | 1 course/request |
| **Reliability** | High (but cascading failures) | Very High |
| **Failure Impact** | All 5 fail together | Only 1 fails |
| **API Calls** | 1 per batch | 1 per course |
| **Rate Limiting** | Low risk | Slight higher risk |
| **Best For** | Speed | Reliability |

### Real-World Example
Processing 100 courses:

**Bulk Mode:**
- 20 batches × 25-40 seconds = 8-13 minutes
- If 1 batch fails: lose 5 courses
- Total success: ~95-99 courses

**Single-Course Mode:**
- 100 courses × 5-10 seconds = 8-17 minutes
- If 1 course fails: lose 1 course
- Total success: ~95-99 courses
- But easier to recover individual failures

---

## Implementation Details

### Code Changes

**config/settings.py**
```python
SINGLE_COURSE_CHECKOUT: bool = False  # New setting
```

**app/services/enrollment_manager.py**

Two new async functions:

```python
async def process_batch():
    """Bulk checkout for 5 courses at once."""
    outcomes = await self.udemy.bulk_checkout(batch)

async def process_single_course(course: Course):
    """Single course checkout with metrics tracking."""
    success = await self.udemy.checkout_single(course)
```

Main enrollment loop:
```python
if use_single_course:
    await process_single_course(course)
else:
    batch.append(course)
    if len(batch) >= ENROLLMENT_BATCH_SIZE:
        await process_batch()
```

### Metrics Output

**Bulk Mode:**
```
📦 Batch Complete: 5/5 enrolled, 0 failed, 28.8s duration
```

**Single-Course Mode:**
```
✅ Single Checkout Success: Course Title (7.3s)
❌ Single Checkout Failed: Course Title (5.1s)
```

---

## Logging Examples

### Enable Single-Course Mode
```
2026-04-23 10:47:15 | INFO | app.services.enrollment_manager:174
🔄 Single-course checkout mode enabled (one at a time)
```

### Processing in Single-Course Mode
```
2026-04-23 10:47:20 | INFO | app.services.enrollment_manager:201
Processing 1/1471: Mastering SEO With ChatGPT
Status: Processing single checkout (Price: 799.0)

2026-04-23 10:47:28 | INFO | app.services.enrollment_manager:221
✅ Single Checkout Success: Mastering SEO With ChatGPT (7.3s)

2026-04-23 10:47:35 | INFO | app.services.enrollment_manager:201
Processing 2/1471: Advanced OSINT Course
Status: Processing single checkout (Price: 999.0)

2026-04-23 10:47:43 | INFO | app.services.enrollment_manager:221
❌ Single Checkout Failed: Advanced OSINT Course (5.1s)
```

### Comparison with Bulk Mode
```
2026-04-23 10:47:15 | INFO | app.services.enrollment_manager:171
🔄 Bulk checkout mode enabled (5 at a time)

2026-04-23 10:47:20 | INFO | app.services.enrollment_manager:201
Processing 1/1471: Mastering SEO With ChatGPT
Status: Added to batch (Price: 799.0)

...add 4 more courses to batch...

2026-04-23 10:47:28 | INFO | app.services.enrollment_manager:224
📦 Batch Complete: 5/5 enrolled, 0 failed, 28.8s duration
```

---

## Decision Tree: Which Mode to Use?

```
                    START
                     |
          Do you need maximum speed?
             /              \
           YES               NO
            |                 |
      Need < 5 min?      Can wait 10-20 min?
       /      \           /        \
     YES      NO        YES        NO
      |        |         |          |
   BULK     BULK?    SINGLE?    ISSUE
   MODE     CHECK   (Maybe)      |
   (Good)   403s             Check if:
   DONE     |              • Datacenter IP
            v              • Getting 403s
         Change            • Cascade failures
         to                 
         SINGLE          If YES → SINGLE
         MODE?           If NO → BULK
```

---

## Configuration Examples

### Docker

**With bulk mode (default):**
```dockerfile
ENV SINGLE_COURSE_CHECKOUT=False
```

**With single-course mode:**
```dockerfile
ENV SINGLE_COURSE_CHECKOUT=True
```

### Docker Compose
```yaml
environment:
  SINGLE_COURSE_CHECKOUT: "True"  # Enable single-course
  FIRECRAWL_API_KEY: "your-key"   # For better reliability
```

### .env File
```bash
# Single-course mode (reliable, slower)
SINGLE_COURSE_CHECKOUT=True

# Or bulk mode (fast, default)
SINGLE_COURSE_CHECKOUT=False
```

### CLI Override (if supported)
```bash
python run.py --single-course-checkout=True
```

---

## Troubleshooting

### Should I use single-course mode?

**YES, if:**
- You're using Firecrawl API key
- You want better reliability
- 403 errors are frequent
- Individual course failures are OK
- Processing speed < 20 min is acceptable

**NO, if:**
- You want maximum speed
- Running on localhost/residential IP
- 403 errors are rare
- Batch failures are acceptable
- Must complete in < 10 min

### Switching Between Modes

To switch modes, simply update the environment variable and restart:

```bash
# Edit .env or environment
SINGLE_COURSE_CHECKOUT=True

# Restart application
docker restart <container_name>
# or
systemctl restart udemy-enroller
# or
python run.py  # with new env var
```

No code changes needed. Both modes are fully compatible.

### Performance Degradation in Single-Course Mode

If single-course mode is slower than expected:
1. Check course validation time (not enrollment)
2. Verify delays between courses (1-3 seconds is normal)
3. Look for repeated 403 errors (use bulk mode if many)
4. Check network latency

---

## Metrics by Mode

### Bulk Mode Metrics
```
📊 Bulk Checkout Metrics: Attempts=2, 403_Recoveries=1, Session_Blocks=0, 
   Total_Delay=7.4s, Success_Rate=100.0%, Duration=28.6s
📦 Batch Complete: 5/5 enrolled, 0 failed, 28.8s duration
```

### Single-Course Mode Metrics
```
✅ Single Checkout Success: Course 1 (7.3s)
✅ Single Checkout Success: Course 2 (6.8s)
❌ Single Checkout Failed: Course 3 (5.1s)
✅ Single Checkout Success: Course 4 (7.5s)
✅ Single Checkout Success: Course 5 (7.1s)
```

---

## Future Enhancements

Potential improvements for single-course mode:

1. **Adaptive Mode Selection**
   - Auto-switch between bulk and single based on 403 frequency
   - Monitor and adjust in real-time

2. **Per-Course Retry Policy**
   - Retry individual failed courses with backoff
   - Keep track of retry count per course

3. **Parallel Single Courses**
   - Process 2-3 courses in parallel instead of sequential
   - Compromise between speed and reliability

4. **Smart Batching**
   - Dynamically adjust batch size based on success rate
   - Start with 5, reduce to 2-3 if too many failures

---

## Summary

| Aspect | Bulk Mode | Single-Course |
|--------|-----------|---------------|
| Configuration | `SINGLE_COURSE_CHECKOUT=False` (default) | `SINGLE_COURSE_CHECKOUT=True` |
| Speed | ⚡ Fast (5 courses/batch) | 🐢 Slower (1 course/request) |
| Reliability | ✅ Good | ✅✅ Excellent |
| Failure Impact | 5 courses fail together | 1 course fails |
| Best For | Speed priority | Reliability priority |
| Recommended | Default, localhost | Datacenter IP + API key |

**No code recompilation needed - just set the environment variable and restart!**
