# Settings UI - Visual Guide

## Settings Page Screenshot (Text Representation)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    ⚙️ Enrollment Settings                                    ║
║                                        [Reset]  [Save Settings]              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║
║ 🌐 Coupon Websites
║ ┌──────────────────────────────────────────────────────────────────────────┐
║ │ ☑ Real Discount    ☑ Courson          ☑ IDownloadCoupons  ☑ E-next      │
║ │ ☑ Discudemy        ☑ Udemy Freebies   ☑ Course Joiner     ☑ Course Vania│
║ └──────────────────────────────────────────────────────────────────────────┘
║
║ 🌍 Languages
║ ┌──────────────────────────────────────────────────────────────────────────┐
║ │ ☑ English  ☑ Spanish  ☑ French  ☑ German  ☑ Russian  ☑ Chinese  ☑ Hindi│
║ └──────────────────────────────────────────────────────────────────────────┘
║
║ 🏷️ Categories
║ ┌──────────────────────────────────────────────────────────────────────────┐
║ │ ☑ Development  ☑ Business  ☑ Design  ☑ Finance & Accounting            │
║ │ ☑ IT & Software  ☑ Marketing  ☑ Personal Development                    │
║ └──────────────────────────────────────────────────────────────────────────┘
║
║ ⚙️ Advanced Settings
║ ┌──────────────────────────────────────────────────────────────────────────┐
║ │
║ │ Enrollment Mode                     Min Rating
║ │ ┌──────────────────────────────────┐ ┌──────────────────────────────────┐
║ │ │ ▼ Bulk (Faster)                  │ │ 0 (0.0 to 5.0)                   │
║ │ └──────────────────────────────────┘ └──────────────────────────────────┘
║ │ Bulk: 5 courses at once (25-40s).     Minimum Rating
║ │ Single: 1 course at a time (5-10s).
║ │
║ │ Batch Size (for Bulk Mode)          Course Updated Within (months)
║ │ ┌──────────────────────────────────┐ ┌──────────────────────────────────┐
║ │ │ 5 (1 to 20)                      │ │ 24 (months)                      │
║ │ └──────────────────────────────────┘ └──────────────────────────────────┘
║ │ Number of courses per batch (1-20)   Exclude courses not updated within
║ │
║ │ Exclude Instructors                 Exclude Title Keywords
║ │ ┌────────────────────────────────┐   ┌────────────────────────────────┐
║ │ │ [john_doe ✕] [jane_smith ✕] │   │ [beginner ✕] [basic ✕]       │
║ │ │ Type and press Enter...        │   │ Type and press Enter...        │
║ │ └────────────────────────────────┘   └────────────────────────────────┘
║ │
║ │ Proxy URL                           Firecrawl API Key
║ │ ┌──────────────────────────────────┐ ┌──────────────────────────────────┐
║ │ │ (Leave blank for direct)         │ │ ••••••••••••••••••••••••••••••  │
║ │ └──────────────────────────────────┘ └──────────────────────────────────┘
║ │ Leave blank for direct connection    Get your key from firecrawl.dev
║ │
║ │ ☑ Save enrolled courses to text file
║ │ ☑ Discounted courses only (skip free)
║ │ ☑ Enable Headless Browser (Slower but more robust)
║ │
║ └──────────────────────────────────────────────────────────────────────────┘
║
║ ⚠️ Danger Zone
║ ┌──────────────────────────────────────────────────────────────────────────┐
║ │ Clear All Enrollment Data
║ │ This will permanently delete all enrollment history, runs, and reset
║ │ your lifetime statistics. This action cannot be undone.
║ │                                              [Clear All Data]            │
║ └──────────────────────────────────────────────────────────────────────────┘
║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## NEW: Enrollment Mode Selection

### Dropdown Options

```
▼ Enrollment Mode
┌─────────────────────────────────────┐
│ Bulk (Faster)                       │
│ Single Course (More Reliable)       │
└─────────────────────────────────────┘
```

### Behavior When Selected

**Option 1: "Bulk (Faster)"**
```
☑ Bulk (Faster) selected
    ↓
Batch Size input SHOWS
┌─────────────────────────────────────┐
│ Batch Size (for Bulk Mode)          │
│ [5           ] (1 to 20)            │
│ Number of courses per batch (1-20)  │
└─────────────────────────────────────┘
```

**Option 2: "Single Course (More Reliable)"**
```
☑ Single Course (More Reliable) selected
    ↓
Batch Size input HIDES
(No batch size field shown)
```

---

## User Flow Example

### Scenario 1: User Wants Faster Enrollment

**Current State:**
```
Enrollment Mode: Single Course (More Reliable)
Batch Size: Hidden
```

**User Action:**
```
1. Click "Enrollment Mode" dropdown
2. Select "Bulk (Faster)"
3. Batch Size field appears showing "5"
4. User adjusts to "10" for faster processing
5. Clicks "Save Settings"
```

**Result:**
```
✅ Settings saved
→ Next enrollment run: 10 courses per batch
→ ~40-60 seconds per batch (faster than 5)
```

### Scenario 2: User Wants More Reliability

**Current State:**
```
Enrollment Mode: Bulk (Faster)
Batch Size: 5
```

**User Action:**
```
1. Click "Enrollment Mode" dropdown
2. Select "Single Course (More Reliable)"
3. Batch Size field hides
4. Clicks "Save Settings"
```

**Result:**
```
✅ Settings saved
→ Next enrollment run: 1 course at a time
→ ~5-10 seconds per course (more reliable)
→ If one fails, other courses still process
```

### Scenario 3: User Wants Conservative Processing

**Current State:**
```
Enrollment Mode: Bulk (Faster)
Batch Size: 5
```

**User Action:**
```
1. Keeps "Bulk (Faster)" selected
2. Changes Batch Size from "5" to "3"
3. Clicks "Save Settings"
```

**Result:**
```
✅ Settings saved
→ Next enrollment run: 3 courses per batch
→ ~15-25 seconds per batch (safer than 5)
→ Balance between speed and reliability
```

---

## Form State Management

### JavaScript State Changes

```javascript
// When page loads:
loadSettings()
  ↓
Fetch from server
  ↓
Set enrollment_mode dropdown value
  ↓
Set batch_size input value
  ↓
Call toggleBatchSizeInput()
  ↓
Show/hide batch_size-container based on mode

// When user changes enrollment mode:
enrollmentModeSelect.addEventListener('change', toggleBatchSizeInput)
  ↓
If mode === 'bulk': batch_size-container.style.display = 'block'
If mode === 'single': batch_size-container.style.display = 'none'

// When user clicks Save:
gatherSettings()
  ↓
Collect all form values including:
  - enrollment_mode (from dropdown)
  - batch_size (from number input)
  ↓
POST to /api/settings/
  ↓
Server validates
  ↓
Save to database
```

---

## Validation Examples

### Valid Inputs ✅

```javascript
// Valid bulk mode with batch size 5
{
  "enrollment_mode": "bulk",
  "batch_size": 5
}

// Valid bulk mode with batch size 20
{
  "enrollment_mode": "bulk",
  "batch_size": 20
}

// Valid single-course mode
{
  "enrollment_mode": "single",
  "batch_size": 5  // Ignored but valid
}
```

### Invalid Inputs ❌

```javascript
// Invalid enrollment mode
{
  "enrollment_mode": "turbo",  // Must be "bulk" or "single"
  "batch_size": 5
}
// Error: 400 Bad Request - enrollment_mode must be 'single' or 'bulk'

// Batch size too small
{
  "enrollment_mode": "bulk",
  "batch_size": 0  // Must be 1-20
}
// Error: 400 Bad Request - batch_size must be between 1 and 20

// Batch size too large
{
  "enrollment_mode": "bulk",
  "batch_size": 50  // Must be 1-20
}
// Error: 400 Bad Request - batch_size must be between 1 and 20

// Non-integer batch size
{
  "enrollment_mode": "bulk",
  "batch_size": "five"  // Must be integer
}
// Error: 400 Bad Request - value must be integer
```

---

## Before & After

### Before This Update

```
Settings Page → Only direct filters (rating, keywords, etc.)
                No control over enrollment strategy
                Enrollment mode controlled by SINGLE_COURSE_CHECKOUT env var
                Batch size hardcoded to 5
                Required app restart to change mode
```

### After This Update

```
Settings Page → All previous filters + NEW enrollment strategy controls
                Users can select mode without restarting
                Users can adjust batch size 1-20
                Per-user settings (each user independent)
                Changes apply to next enrollment immediately
```

---

## CSS Classes (Tailwind)

```html
<!-- Main container -->
<div class="bg-gray-800 rounded-xl p-6 border border-gray-700 mb-6">

  <!-- Section title -->
  <h2 class="text-lg font-semibold text-white mb-4">
    <i class="fas fa-sliders-h mr-2 text-cyan-400"></i>Advanced Settings
  </h2>

  <!-- Grid layout: 1 col mobile, 2 cols desktop -->
  <div class="grid grid-cols-1 md:grid-cols-2 gap-6">

    <!-- Individual setting container -->
    <div>
      <label class="block text-sm font-medium text-gray-300 mb-2">
        Enrollment Mode
      </label>
      <select class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500">
        ...
      </select>
      <p class="text-xs text-gray-500 mt-1">Help text...</p>
    </div>
  </div>
</div>
```

---

## Summary

The Settings UI now provides:

✅ **Dropdown selection** for Enrollment Mode (Bulk/Single)  
✅ **Number input** for Batch Size (1-20), shown only in Bulk mode  
✅ **Real-time toggle** of batch size visibility based on mode  
✅ **Form validation** on both client and server  
✅ **Instant UI feedback** on save/error  
✅ **Responsive design** (mobile-friendly)  
✅ **Descriptive help text** for each setting  

Users can now control enrollment strategy directly from the Settings page without any technical knowledge or server configuration!
