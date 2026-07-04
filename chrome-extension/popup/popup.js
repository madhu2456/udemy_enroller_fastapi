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
  cookies.forEach(c => cookieMap[c.name] = c.value);

  const hasAllCookies = REQUIRED_COOKIES.every(name => cookieMap[name]);

  if (hasAllCookies) {
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

// Format cookies for clipboard
function formatCookies(cookies) {
  return REQUIRED_COOKIES
    .map(name => `${name}=${cookies[name]}`)
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
    chrome.runtime.sendMessage({ action: 'getCouponCount' }, (response) => {
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
    setTimeout(hideStatus, 2000);
  } else {
    showStatus('error', 'Failed to copy. Try again.');
  }
});

// Login to enroller handler
loginBtn.addEventListener('click', async () => {
  const status = await checkLoginStatus();

  if (!status.loggedIn) {
    showStatus('error', 'Not logged into Udemy');
    return;
  }

  showStatus('loading', 'Opening Enroller...');

  const formatted = formatCookies(status.cookies);

  // Open enroller with cookies in URL (for manual paste)
  chrome.tabs.create({ url: `${ENROLLER_URL}/#connect` });
  window.close();
});

// Initialize
document.addEventListener('DOMContentLoaded', updateUI);
