// Udemy Enroller - Background Service Worker

// Fetch coupon count (called from popup on-demand)
async function fetchCouponCount() {
  try {
    const response = await fetch('https://udemyenroller.madhudadi.in/udemycoupons/api/coupons?limit=1');
    if (response.ok) {
      const data = await response.json();
      return data.total || 0;
    }
  } catch (err) {
    // Silently fail - optional feature
  }
  return null;
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getCouponCount') {
    fetchCouponCount().then(count => {
      sendResponse({ count });
    }).catch(() => {
      sendResponse({ count: null });
    });
    return true; // Keep message channel open for async response
  }
});
