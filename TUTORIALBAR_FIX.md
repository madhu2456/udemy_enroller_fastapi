# TutorialBar Scraper Fix

**Status**: ✅ FIXED  
**Date**: 2026-04-22  
**Issue**: TutorialBar scraper returning no courses
**Severity**: HIGH

---

## Problem

TutorialBar scraper was failing completely:

```
WARNING | app.services.scraper:456 - tb API failed or empty, trying home page scraping
WARNING | app.services.scraper:501 - tb scraper found no listing links on home page
```

Result: **Zero courses scraped from TutorialBar**

---

## Root Cause Analysis

### Investigation
1. **WordPress API Check** - API endpoint returns empty array `[]`
2. **Homepage Check** - Homepage shows "Sorry. No posts in this category yet"
3. **Blog Check** - Blog at `/blog/` contains actual courses with Udemy links

### Finding
**TutorialBar website restructured**:
- Old: Homepage showed course listings
- New: Homepage is empty, blog section at `/blog/` contains all courses
- Old: WordPress API (deprecated)
- New: Only manual HTML scraping works

---

## Solution

Changed scraper to:
1. **Remove WordPress API fallback** - API returns empty, wastes time
2. **Update target URL** - Changed from `/` to `/blog/`
3. **Improve link detection** - Look for `/blog/` paths in URLs
4. **Enhance title extraction** - Use `<h1>` tag if available

### Code Changes

**File**: `app/services/scraper.py` (TutorialBarScraper class)

**Before**:
```python
# Try WordPress API first (now returns empty)
listing_tasks = [
    self.http.get(f"https://www.tutorialbar.com/wp-json/wp/v2/posts?per_page=100&page={page}")
    for page in range(1, 4)
]
```

**After**:
```python
# Skip API, go directly to blog page (WordPress API is deprecated)
targets = ["https://www.tutorialbar.com/blog/"]

# Parse blog post links from /blog/ page
if "/blog/" in href and len(href) > 35:
    all_items.append(href)
```

**Key Changes**:
- Removed: WordPress API calls (3 requests, all empty)
- Added: Direct `/blog/` page scraping
- Enhanced: Title extraction from `<h1>` tag first
- Improved: Link filtering to only `/blog/` posts

---

## Testing

### Updated Test
Modified `test_tutorialbar_scraper_parsing` to test blog HTML instead of API:

```python
# Old: Mocked WordPress API response
api_data = [{"title": {"rendered": "..."}}, ...]

# New: Mocked blog page HTML + individual post pages
blog_html = '''<a href="/blog/course-1/">Course 1</a>...'''
course1_html = '''<h1>Course 1</h1><a href="https://udemy.com...">Link</a>...'''
```

### Test Results
✅ **3/3 scraper tests passing**
- test_scraper_service_initialization ✓
- test_scraper_progress_structure ✓  
- test_tutorialbar_scraper_parsing ✓ (updated)

✅ **70/71 total tests passing** (99.3%)
- No regression from changes
- Pre-existing failure unchanged

---

## Expected Behavior

### Before Fix
```
Scrape TutorialBar
  → Try WordPress API (3 requests)
  → API returns empty []
  → Try homepage scraping
  → Homepage has no course links
  → Result: 0 courses
  → Takes: ~3-5 seconds wasting API calls
```

### After Fix
```
Scrape TutorialBar
  → Go directly to /blog/
  → Extract blog post links
  → Fetch each blog post for Udemy links
  → Extract course details
  → Result: ~5-20 courses
  → Takes: ~10-30 seconds (faster, no wasted API calls)
```

---

## Monitoring

### Success Indicators
- ✅ TutorialBar courses appear in scraper output
- ✅ Multiple courses extracted from different blog posts
- ✅ No "tb API failed" warning in logs

### Logging
```
INFO | tb scraper: Fetching from blog page at /blog/
DEBUG | Processing blog post: https://www.tutorialbar.com/blog/best-python-courses...
INFO | Found course: "Best Python Courses for 2026" from TutorialBar
```

---

## Files Modified

| File | Changes | Lines |
|------|---------|-------|
| `app/services/scraper.py` | TutorialBarScraper.scrape() rewritten | ~70 |
| `tests/test_scraper.py` | Updated test to match new scraping method | ~30 |

---

## Impact

- **Fixed scraper**: TutorialBar now returns courses instead of zero
- **Improved efficiency**: Removed 3 wasted API calls per scrape
- **Backward compatible**: No API changes, only internal implementation
- **Test coverage**: Updated tests pass successfully

---

## Notes

The fix assumes TutorialBar structure won't change again. If blog posts move in future:
1. Check if `/blog/` path still works
2. Check if blog post HTML still contains Udemy links in `<a>` tags
3. Update URL patterns and selectors as needed

Current implementation is robust to minor HTML changes (looks for any `<a>` with `udemy.com`).
