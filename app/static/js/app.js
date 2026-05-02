// Global app utilities

window.csrfToken = null;

function getCsrfToken() {
    if (window.csrfToken) return window.csrfToken;
    const match = document.cookie.match(new RegExp('(^| )csrf_token=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : null;
}

async function apiFetch(url, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
        options.headers = options.headers || {};
        const token = getCsrfToken();
        if (token) {
            options.headers['X-CSRF-Token'] = token;
        }
    }
    return fetch(url, options);
}

async function logout() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);
        
        const response = await apiFetch('/api/auth/logout', { 
            method: 'POST',
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        
        if (response.ok) {
            console.log('Logout successful');
        } else {
            console.warn('Logout returned status:', response.status);
        }
    } catch (e) {
        console.warn('Logout request failed or timed out:', e);
    }
    
    window.csrfToken = null;
    localStorage.clear();
    sessionStorage.clear();
    
    document.cookie.split(";").forEach(c => {
        const [name] = c.split("=");
        document.cookie = `${name.trim()}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`;
    });
    
    window.location.href = '/';
}

// Highlight active nav link
document.addEventListener('DOMContentLoaded', () => {
    const path = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
        const href = link.getAttribute('href');
        if (href === path || (href === '/' && path === '/')) {
            link.classList.add('active');
        }
    });
});

// Toast notification utility
function showToast(message, type = 'info') {
    const colors = {
        success: 'bg-green-800 text-green-200 border border-green-600',
        error: 'bg-red-800 text-red-200 border border-red-600',
        info: 'bg-blue-800 text-blue-200 border border-blue-600',
        warning: 'bg-yellow-800 text-yellow-200 border border-yellow-600',
    };
    const toast = document.createElement('div');
    toast.className = `toast ${colors[type] || colors.info}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
