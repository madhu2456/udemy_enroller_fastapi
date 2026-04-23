// Global app utilities

async function logout() {
    try {
        // Use a timeout for the logout request so it doesn't hang the UI if the server is busy
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);
        
        const response = await fetch('/api/auth/logout', { 
            method: 'POST',
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        
        // Log result
        if (response.ok) {
            console.log('Logout successful');
        } else {
            console.warn('Logout returned status:', response.status);
        }
    } catch (e) {
        console.warn('Logout request failed or timed out:', e);
    }
    
    // Clear any client-side data
    localStorage.clear();
    sessionStorage.clear();
    
    // Clear all cookies by setting them to expire
    document.cookie.split(";").forEach(c => {
        const [name] = c.split("=");
        document.cookie = `${name.trim()}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`;
    });
    
    // Force page refresh to clear session completely
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
