// Global app utilities

async function logout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {}
    window.location.href = '/login';
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
