// Udemy Enroller - Cookie Extractor Popup Script

const UDEMY_DOMAIN = 'udemy.com';
const UDEMY_URL = 'https://www.udemy.com';
const ENROLLER_URL = 'https://udemyenroller.madhudadi.in';

// Cookie names we need
const REQUIRED_COOKIES = ['access_token', 'client_id', 'csrftoken'];

// DOM Elements
const statusEl = document.getElementById('status');
const statusIcon = document.getElementById('status-icon');
const statusText = document.getElementById('status-text');
const notLoggedInEl = document.getElementById('not-logged-in');
const loggedInEl = document.getElementById('logged-in');
const userEmailEl = document.getElementById('user-email');
const couponBadgeEl = document.getElementById('coupon-count');
const couponNumberEl = document.getElementById('coupon-number');
const copyBtn = document.getElementById('copy-btn');
const loginBtn = document.getElementById('login-btn');
const previewEl = document.getElementById('preview');

// Show status message
function showStatus(type, message) {
  statusEl.classList.remove('hidden', 'success', 'error', 'loading');
  statusEl.classList.add(type);
  statusIcon.textContent = type === 'success' ? '✓' : type === 'error' ? '✗' : '⟳';
  statusText.textContent = message;
}

// Hide status
function hideStatus() {
  statusEl.classList.add('hidden');
}

// Get all Udemy cookies
async function getUdemyCookies() {
  return new Promise((resolve) => {
    chrome.cookies.getAll({ domain: UDEMY_DOMAIN }, (cookies) => {
      resolve(cookies);
    });
  });
}

// Check if user is logged in
async function checkLoginStatus() {
  const cookies = await getUdemyCookies();
  const cookieMap = {};
  const cookieDetails = {};
  cookies.forEach(c => {
    cookieMap[c.name] = c.value;
    cookieDetails[c.name] = c;
  });

  const hasAllCookies = REQUIRED_COOKIES.every(name => cookieMap[name]);

  if (hasAllCookies) {
    // Check if any required cookie is expired
    const now = Date.now() / 1000;
    const expiredCookies = REQUIRED_COOKIES.filter(name => {
      const cookie = cookieDetails[name];
      return cookie && cookie.expirationDate && cookie.expirationDate < now;
    });

    if (expiredCookies.length > 0) {
      return {
        loggedIn: false,
        cookies: null,
        email: null,
        error: 'Session expired. Please refresh udemy.com and try again.'
      };
    }

    // Extract user info from cookies if available
    const userEmail = cookieMap['user_email'] || 'Logged in';
    return {
      loggedIn: true,
      cookies: cookieMap,
      email: userEmail
    };
  }

  return { loggedIn: false, cookies: null, email: null };
}

// Map cookie names to web app field names
const COOKIE_NAME_MAP = {
  'access_token': 'access_token',
  'client_id': 'client_id',
  'csrftoken': 'csrf_token'
};

function formatCookies(cookies) {
  return REQUIRED_COOKIES
    .map(name => {
      const fieldName = COOKIE_NAME_MAP[name] || name;
      return `${fieldName}=${encodeURIComponent(cookies[name])}`;
    })
    .join('&');
}

// Copy to clipboard with fallback
async function copyToClipboard(text) {
  try {
    // Modern API
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    // Fallback for older browsers
    try {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      return true;
    } catch (fallbackErr) {
      return false;
    }
  }
}

// Fetch coupon count from background service worker
async function fetchCouponCount() {
  return new Promise((resolve) => {
    // Set timeout in case service worker is slow
    const timeout = setTimeout(() => resolve(null), 3000);
    
    chrome.runtime.sendMessage({ action: 'getCouponCount' }, (response) => {
      clearTimeout(timeout);
      
      // Check for extension errors
      if (chrome.runtime.lastError) {
        resolve(null);
        return;
      }
      
      if (response && response.count !== undefined) {
        resolve(response.count);
      } else {
        resolve(null);
      }
    });
  });
}

// Update UI with login status
async function updateUI() {
  const status = await checkLoginStatus();

  if (status.loggedIn) {
    notLoggedInEl.classList.add('hidden');
    loggedInEl.classList.remove('hidden');
    loginBtn.classList.remove('hidden');
    userEmailEl.textContent = status.email;

    // Update preview
    const formatted = formatCookies(status.cookies);
    previewEl.textContent = formatted.substring(0, 50) + '...';

    // Fetch coupon count (optional)
    const count = await fetchCouponCount();
    if (count !== null) {
      couponNumberEl.textContent = count.toLocaleString();
      couponBadgeEl.classList.remove('hidden');
    }
  } else {
    notLoggedInEl.classList.remove('hidden');
    loggedInEl.classList.add('hidden');
    
    // Show specific error message if available
    if (status.error) {
      showStatus('error', status.error);
    }
  }
}

// Copy cookies handler
copyBtn.addEventListener('click', async () => {
  const status = await checkLoginStatus();

  if (!status.loggedIn) {
    showStatus('error', 'Not logged into Udemy');
    return;
  }

  showStatus('loading', 'Copying...');

  const formatted = formatCookies(status.cookies);
  const success = await copyToClipboard(formatted);

  if (success) {
    showStatus('success', 'Cookies copied to clipboard!');
    setTimeout(hideStatus, 4000);
  } else {
    showStatus('error', 'Failed to copy. Try again.');
  }
});

// Open enroller dashboard handler
loginBtn.addEventListener('click', async () => {
  // Open enroller web app - user will paste cookies manually
  chrome.tabs.create({ url: `${ENROLLER_URL}/#connect` });
  window.close();
});

// Initialize
document.addEventListener('DOMContentLoaded', updateUI);
