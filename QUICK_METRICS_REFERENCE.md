# Quick Metrics Reference Card

## Metrics Format

### Bulk Checkout Metrics (📊)
```
📊 Bulk Checkout Metrics: Attempts=X, 403_Recoveries=Y, Session_Blocks=Z, 
   Total_Delay=Xs, Success_Rate=X%, Duration=Xs
```

### Batch Processing Metrics (📦)
```
📦 Batch Complete: X/Y enrolled, Z failed, Xs duration
```

---

## One-Minute Interpretation Guide

| Scenario | Log Output | Status | Action |
|----------|-----------|--------|--------|
| **All Good** | `Success_Rate=100%, 403_Recoveries=0, Session_Blocks=0` | ✅ | Continue |
| **Minor Issue** | `Success_Rate=100%, 403_Recoveries=1, Session_Blocks=0` | ⚠️ | Monitor |
| **Degraded** | `Success_Rate=60%, 403_Recoveries=2, Session_Blocks=0` | ⚠️ | Consider API key |
| **Unstable** | `Success_Rate=40%, 403_Recoveries=3, Session_Blocks=0` | ❌ | Use API key |
| **Blocked** | `Success_Rate=0%, Session_Blocks=1` | ❌ | API key or wait 30min |

---

## Search Commands

### Show All Metrics
```bash
grep "📊" logfile.txt                    # Bulk checkout metrics
grep "📦" logfile.txt                    # Batch summaries
grep -E "(📊|📦)" logfile.txt            # Both
```

### Find Problems
```bash
grep "Session_Blocks=[1-9]" logfile.txt            # IP blocked
grep "403_Recoveries=[3-9]" logfile.txt           # Unstable session
grep "Success_Rate=[0-4][0-9]\." logfile.txt      # Low success
```

### Calculate Stats
```bash
# Success rate average
grep "Success_Rate=" logfile.txt | grep -oP 'Success_Rate=\K[0-9.]+' | \
  awk '{sum+=$1; count++} END {print "Avg:", sum/count "%"}'

# Total 403 recoveries
grep "403_Recoveries=" logfile.txt | grep -oP '403_Recoveries=\K[0-9]+' | \
  awk '{sum+=$1} END {print "Total:", sum}'

# Batches that failed completely
grep "Success_Rate=0%" logfile.txt | wc -l
```

---

## Metric Definitions

| Metric | Meaning | Good | Warning | Bad |
|--------|---------|------|---------|-----|
| **Attempts** | Checkout tries | 1-2 | 3-5 | >5 |
| **403_Recoveries** | CSRF refreshes | 0-1 | 2-3 | >3 |
| **Session_Blocks** | IP blocks | 0 | - | >0 |
| **Total_Delay** | Wait time | <10s | 10-20s | >20s |
| **Success_Rate** | % enrolled | >90% | 70-90% | <50% |
| **Duration** | Batch time | <2min | 2-3min | >3min |
| **Enrolled/Failed** | Batch results | 5/5 enrolled | 3-4/5 | <3/5 |

---

## Common Patterns

### Pattern 1: Perfect Run
```
📊 Bulk Checkout Metrics: Attempts=1, 403_Recoveries=0, Session_Blocks=0, 
   Total_Delay=2.1s, Success_Rate=100.0%, Duration=18.3s
📦 Batch Complete: 5/5 enrolled, 0 failed, 18.5s duration
```
**Meaning:** No issues. IP/session is healthy.

### Pattern 2: One Transient 403
```
📊 Bulk Checkout Metrics: Attempts=2, 403_Recoveries=1, Session_Blocks=0, 
   Total_Delay=7.4s, Success_Rate=100.0%, Duration=28.6s
📦 Batch Complete: 5/5 enrolled, 0 failed, 28.8s duration
```
**Meaning:** Minor rate limit. Recovered fine. All enrolled.

### Pattern 3: Multiple 403s
```
📊 Bulk Checkout Metrics: Attempts=4, 403_Recoveries=3, Session_Blocks=0, 
   Total_Delay=16.2s, Success_Rate=60.0%, Duration=42.1s
📦 Batch Complete: 3/5 enrolled, 2 failed, 42.3s duration
```
**Meaning:** Session unstable. Some courses failed. Add API key.

### Pattern 4: IP Blocked
```
✗ Too many 403 errors (4) on bulk checkout. Session may be blocked.
📊 Bulk Checkout Metrics: Attempts=4, 403_Recoveries=0, Session_Blocks=1, 
   Total_Delay=18.9s, Success_Rate=0.0%, Duration=35.7s
📦 Batch Complete: 0/5 enrolled, 5 failed, 36.0s duration
```
**Meaning:** IP detected. Use API key or wait 30+ minutes.

---

## Decision Tree

```
                   Start Monitoring Logs
                           |
                  See "📊 Bulk Checkout"?
                       /        \
                     Yes         No → Keep waiting
                      |
            Check Success_Rate
             /          |          \
          >85%        50-85%      <50%
          /              |           \
        ✅               ⚠️            ❌
       All Good    Check 403_Recoveries  Check Session_Blocks
                          |                   |
                    <2? Good, Monitor    >0? Need API Key
                    >2? Watch closely        or Wait
                    >3? Add API Key
```

---

## Monitoring Intervals

### Real-Time (First Run)
Watch logs continuously:
```bash
docker logs -f <container> 2>&1 | grep -E "(📊|📦|ERROR|403)"
```

### Hourly Check
Summarize metrics:
```bash
grep "📊" logfile.txt | tail -5          # Last 5 batches
grep "Session_Blocks=[1-9]" logfile.txt  # Any blocks?
grep "Success_Rate=[0-4][0-9]" logfile.txt | wc -l  # Failed batches
```

### Daily Analysis
Calculate averages:
```bash
# Average success rate
grep "Success_Rate=" logfile.txt | grep -oP 'Success_Rate=\K[0-9.]+' | \
  awk '{sum+=$1; count++} END {print count " batches, avg:", sum/count "%"}'

# Total 403 recoveries
grep "403_Recoveries=" logfile.txt | grep -oP '403_Recoveries=\K[0-9]+' | \
  awk '{sum+=$1} END {print "Total 403 recoveries:", sum}'
```

---

## API Key Decision

Add Firecrawl API key when you see **ANY** of:
- ✗ `Session_Blocks > 0` - IP detected
- ✗ `Success_Rate < 70%` for 3+ consecutive batches
- ✗ `403_Recoveries > 2` in a single batch
- ✗ Multiple "Too many 403 errors" messages

Keep free solution when you see:
- ✅ `Success_Rate > 85%` consistently
- ✅ `403_Recoveries < 1` per batch
- ✅ `Session_Blocks = 0` always
- ✅ No "Too many 403 errors" messages

---

## Docker Log Commands

### Show All Metrics
```bash
docker logs <container_name> 2>&1 | grep "📊"
docker logs <container_name> 2>&1 | grep "📦"
```

### Follow Real-Time
```bash
docker logs -f <container_name> 2>&1 | grep -E "(📊|📦)"
docker logs -f <container_name> 2>&1 | grep -E "(ERROR|403)" 
```

### Search History
```bash
docker logs <container_name> 2>&1 | grep "Success_Rate=0%"
docker logs <container_name> 2>&1 | grep "Session_Blocks=[1-9]"
```

---

## File Log Commands

### Show Last 10 Batches
```bash
grep "📊" /path/to/logs/app.log | tail -10
grep "📦" /path/to/logs/app.log | tail -10
```

### Count by Status
```bash
# Perfect batches (100% success)
grep "Success_Rate=100" /path/to/logs/app.log | wc -l

# Failed batches (0% success)
grep "Success_Rate=0" /path/to/logs/app.log | wc -l

# Medium success (50-80%)
grep "Success_Rate=[5-7][0-9]\." /path/to/logs/app.log | wc -l
```

---

## Troubleshooting Checklist

- [ ] Can I see `📊 Bulk Checkout Metrics` in logs?
- [ ] Is `Success_Rate` > 50%?
- [ ] Is `Session_Blocks = 0`?
- [ ] Are `403_Recoveries` < 2 per batch?
- [ ] Is duration < 3 minutes per batch?

**If all YES:** System working normally ✅
**If any NO:** Consider adding Firecrawl API key

---

## Quick Grep Alias (Optional)

Add to `.bashrc` or `.zshrc`:
```bash
alias metrics-show='grep -E "(📊|📦)" /path/to/logs/app.log'
alias metrics-errors='grep -E "(Session_Blocks|403_Recoveries|Success_Rate=0)" /path/to/logs/app.log'
alias metrics-stat='grep "Success_Rate=" /path/to/logs/app.log | grep -oP "Success_Rate=\K[0-9.]+" | awk "{sum+=\$1; count++} END {print \"Avg:\", sum/count \"%\"}"'
```

Then:
```bash
metrics-show                # See all metrics
metrics-errors              # See problems
metrics-stat                # Calculate average
```

---

## Export Metrics to CSV (Advanced)

```bash
grep "📊" logfile.txt | awk -F'[=,]' '{
  print $2 "," $3 "," $4 "," $5 "," $6 "," $7
}' | sed 's/^ *//g' > metrics.csv
```

Then open in Excel/Sheets for trending analysis.

---

## Summary

**Metrics are your feedback loop:**
- <1 min: See if batch succeeded or failed
- <5 min: Understand what happened
- <1 hour: Make decision on API key
- <1 day: Analyze trends

Keep monitoring until `Success_Rate` consistently > 85% and `Session_Blocks = 0`.

---

**Last Updated:** 2026-04-23  
**Version:** 1.0  
**Status:** Production Ready ✅
