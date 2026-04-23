# Monitoring & Metrics Guide

## Overview
The Udemy Enroller now tracks detailed metrics at both the **bulk checkout** and **batch processing** levels to help monitor Cloudflare bypass effectiveness and diagnose 403 errors.

---

## Bulk Checkout Metrics

Every bulk checkout operation logs a metrics summary at the end with:

```
📊 Bulk Checkout Metrics: Attempts=7, 403_Recoveries=2, Session_Blocks=0, 
   Total_Delay=18.3s, Success_Rate=80.0%, Duration=45.2s
```

### Metric Descriptions

| Metric | Description | Good Value | Warning Value |
|--------|-------------|-----------|---------------|
| **Attempts** | Total checkout attempts made | 1-3 | >7 (many retries needed) |
| **403_Recoveries** | Times CSRF was refreshed due to 403 | 0-2 per batch | >3 (session unstable) |
| **Session_Blocks** | Times max consecutive 403s exceeded | 0 | >0 (IP may be blocked) |
| **Total_Delay** | Total wait time across all attempts | < batch_size × 5s | > batch_size × 10s |
| **Success_Rate** | Percentage of courses successfully enrolled | >80% | <50% (major issue) |
| **Duration** | Total time for entire batch | < 2 min per 5 courses | > 3 min per 5 courses |

### Examples

**Good batch (free solution)**:
```
Attempts=3, 403_Recoveries=1, Session_Blocks=0, Total_Delay=8.2s, 
Success_Rate=100%, Duration=22.5s
```
- One 403 error recovered via CSRF refresh
- All courses enrolled successfully
- Normal delays working as expected

**Problem batch (datacenter IP)**:
```
Attempts=4, 403_Recoveries=0, Session_Blocks=1, Total_Delay=15.1s, 
Success_Rate=20%, Duration=38.4s
```
- Session blocked after 4 attempts
- Only 1 out of 5 courses enrolled
- **Action needed**: May need Firecrawl API key or retry later

---

## Batch Processing Metrics

Each batch completion also logs summary:

```
📦 Batch Complete: 5/5 enrolled, 0 failed, 24.7s duration
```

### Interpretation

| Enrolled | Failed | Status | Recommendation |
|----------|--------|--------|-----------------|
| 5/5 | 0 | ✓ Perfect | Continue as-is |
| 4/5 | 1 | ✓ Good | Check failed course details |
| 3/5 | 2 | ⚠ Fair | Retry batch or check IP block |
| 2/5 | 3 | ✗ Poor | Likely IP blocked or session invalid |
| 0/5 | 5 | ✗ Critical | Restart service or check Cloudflare |

---

## Real-World Examples from Production Logs

### Scenario 1: Successful Batch (Localhost/Residential IP)
```
📊 Bulk Checkout Metrics: Attempts=1, 403_Recoveries=0, Session_Blocks=0, 
   Total_Delay=2.1s, Success_Rate=100%, Duration=18.3s
📦 Batch Complete: 5/5 enrolled, 0 failed, 18.5s duration
```
**Interpretation**: Perfect operation. No retries needed, all courses enrolled.

### Scenario 2: One 403 Recovery (Common on Servers)
```
📊 Bulk Checkout Metrics: Attempts=2, 403_Recoveries=1, Session_Blocks=0, 
   Total_Delay=7.4s, Success_Rate=100%, Duration=28.6s
📦 Batch Complete: 5/5 enrolled, 0 failed, 28.8s duration
```
**Interpretation**: One transient 403 error (likely rate limit). CSRF refresh recovered. All courses enrolled.

### Scenario 3: Repeated 403s (Session Unstable)
```
📊 Bulk Checkout Metrics: Attempts=4, 403_Recoveries=3, Session_Blocks=0, 
   Total_Delay=16.2s, Success_Rate=60%, Duration=42.1s
📦 Batch Complete: 3/5 enrolled, 2 failed, 42.3s duration
```
**Interpretation**: Session became unstable. Multiple 403 recoveries helped but 2 courses still failed. May need restart or API key.

### Scenario 4: Session Blocked (Datacenter IP Detected)
```
📊 Bulk Checkout Metrics: Attempts=4, 403_Recoveries=0, Session_Blocks=1, 
   Total_Delay=18.9s, Success_Rate=0%, Duration=35.7s
📦 Batch Complete: 0/5 enrolled, 5 failed, 36.0s duration
```
**Interpretation**: All attempts hit 403, no recovery possible. Session blocked. **Action**: Use Firecrawl API key or retry in 30+ minutes.

---

## Monitoring Dashboard (Optional)

For continuous monitoring, parse logs for these patterns:

### Per-Batch Tracking
```bash
# Extract all batch metrics
grep "📊 Bulk Checkout Metrics" logfile.txt

# Count successful vs failed batches
grep "Success_Rate=100%" logfile.txt | wc -l  # Perfect batches
grep "Success_Rate=0%" logfile.txt | wc -l    # Failed batches
```

### 403 Error Tracking
```bash
# Find sessions with multiple 403 recoveries
grep "403_Recoveries=[3-9]" logfile.txt | tail -5

# Find session blocks
grep "Session_Blocks=[1-9]" logfile.txt | tail -5
```

### Average Metrics
```bash
# Average success rate across all batches
grep "Success_Rate=" logfile.txt | grep -oP 'Success_Rate=\K[0-9.]+' | awk '{sum+=$1; count++} END {print "Avg:", sum/count "%"}'

# Total 403 recoveries
grep "403_Recoveries=" logfile.txt | grep -oP '403_Recoveries=\K[0-9]+' | awk '{sum+=$1} END {print "Total 403 Recoveries:", sum}'
```

---

## Troubleshooting Based on Metrics

### High `403_Recoveries` (3+)
**Symptom**: Many CSRF token refreshes needed
- **Cause**: Rate limiting or unstable session
- **Fix**: 
  1. Increase batch delay (currently 2-5s, try 5-10s)
  2. Enable Firecrawl API key
  3. Check if running on datacenter IP

### `Session_Blocks` > 0
**Symptom**: Max consecutive 403s exceeded, IP blocked
- **Cause**: Udemy detected automated traffic from datacenter IP
- **Fix**:
  1. Add Firecrawl API key (bypasses all 403s)
  2. Wait 30+ minutes before retrying
  3. Use residential proxy if available

### `Success_Rate` < 50%
**Symptom**: Most courses failing to enroll
- **Cause**: Session invalid, CSRF token issues, or IP blocked
- **Fix**:
  1. Re-authenticate (login again)
  2. Check browser cookies are valid
  3. Verify CSRF token appears in logs (should see "reusing provided token")

### High `Total_Delay` vs `Duration`
**Symptom**: Delays taking up most of processing time
- **Cause**: Adaptive backoff multiplier is high (multiple consecutive 403s)
- **Fix**:
  1. Check batch size (smaller batches = fewer delays)
  2. Verify network latency not excessive
  3. Consider API key if 403s persistent

---

## Key Monitoring Questions

**Q: What's the target success rate?**
A: >85% indicates healthy operation. <50% indicates major issues.

**Q: How many 403 recoveries is normal?**
A: 0-1 per batch is normal. 2+ suggests rate limiting. 3+ suggests session issues.

**Q: When should I use Firecrawl?**
A: Add API key when `Session_Blocks` > 0 or `Success_Rate` consistently < 70%.

**Q: Can I reduce delays?**
A: Safe limits are 1-2s between requests, 2-5s between batches. Going lower increases 403 risk.

---

## Implementation Details

### Metrics Tracking (udemy_client.py)
```python
metrics = {
    "total_attempts": 0,
    "successful_403_recoveries": 0,
    "failed_checkouts": 0,
    "session_blocks": 0,
    "total_delay_time": 0.0,
    "start_time": asyncio.get_event_loop().time()
}
```

### Batch Tracking (enrollment_manager.py)
```python
batch_start = asyncio.get_event_loop().time()
outcomes = await self.udemy.bulk_checkout(batch)
batch_duration = asyncio.get_event_loop().time() - batch_start
enrolled = sum(1 for status in outcomes.values() if status == "enrolled")
```

---

## Metrics Retention

Metrics are logged to both:
- **Console logs**: Real-time monitoring via `docker logs` or terminal
- **Application logs**: Persistent storage in log files for analysis

### Log Locations
- **Docker**: `docker logs <container_name> 2>&1 | grep "📊"`
- **Files**: Check application log file location (set in environment)

---

## Future Enhancements

Planned monitoring improvements:
- [ ] JSON metrics export for monitoring dashboards (Prometheus, DataDog)
- [ ] Per-course success tracking (not just batch-level)
- [ ] Cloudflare detection analytics (how often challenges occur)
- [ ] Adaptive threshold adjustment (auto-increase delays if 403_Recoveries high)
