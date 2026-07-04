// Udemy Enroller - Background Service Worker

// Cache for coupon count
let couponCountCache = {
  count: null,
  timestamp: 0
};

const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

// Fetch coupon count (called from popup or on alarm)
async function fetchCouponCount() {
  // Check cache first
  if (couponCountCache.count !== null && 
      Date.now() - couponCountCache.timestamp < CACHE_TTL) {
    return couponCountCache.count;
  }

  try {
    const response = await fetch('https://udemyenroller.madhudadi.in/udemycoupons/api/coupons?limit=1');
    if (response.ok) {
      const data = await response.json();
      couponCountCache = {
        count: data.total || 0,
        timestamp: Date.now()
      };
      return couponCountCache.count;
    }
  } catch (err) {
    // Silently fail
  }
  return null;
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getCouponCount') {
    fetchCouponCount().then(count => {
      sendResponse({ count });
    });
    return true; // Keep message channel open for async response
  }
});

// Create alarm on install only
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create('refreshCouponCount', { periodInMinutes: 30 });
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'refreshCouponCount') {
    fetchCouponCount();
  }
});
