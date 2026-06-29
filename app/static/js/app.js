// Global app utilities

window.csrfToken = null;

function getCsrfToken() {
  if (window.csrfToken) return window.csrfToken;

  // Read CSRF token from cookie
  const match = document.cookie.match(new RegExp("(^| )csrf_token=([^;]+)"));
  if (match) {
    window.csrfToken = decodeURIComponent(match[2]);
    return window.csrfToken;
  }

  return null;
}

async function apiFetch(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  if (["POST", "PUT", "DELETE", "PATCH"].includes(method)) {
    options.headers = options.headers || {};
    const token = getCsrfToken();
    if (token) {
      options.headers["X-CSRF-Token"] = token;
    }
  }
  return fetch(url, options);
}

async function logout() {
  try {
    showToast("Logging out...", "info");

    const controller = new AbortController();
    // A generous 10-second timeout to allow the backend to gracefully close the Udemy HTTP client session
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    const response = await apiFetch("/api/auth/logout", {
      method: "POST",
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (response.ok) {
      console.log("Logout successful");
      handleSuccessfulLogout();
    } else {
      console.warn("Logout returned status:", response.status);
      // Handle cases where the session was already cleaned up on the server (401/403)
      if (response.status === 401 || response.status === 403) {
        console.log(
          "Session invalid on server, clearing frontend cookies anyway.",
        );
        handleSuccessfulLogout();
      } else {
        showToast("Logout failed. Please try again.", "error");
      }
    }
  } catch (e) {
    console.warn("Logout request failed or timed out:", e);
    if (e.name === "AbortError") {
      showToast("Logout request timed out. Please try again.", "error");
    } else {
      showToast("Connection error. Logout failed.", "error");
    }
  }
}

function handleSuccessfulLogout() {
  window.csrfToken = null;
  try {
    localStorage.clear();
    sessionStorage.clear();
  } catch (e) {
    console.warn("Error clearing storage:", e);
  }

  // Clear cookies by setting their expiration date to the past under both root and API paths
  document.cookie.split(";").forEach((c) => {
    const [name] = c.split("=");
    const trimmedName = name.trim();
    document.cookie = `${trimmedName}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`;
    document.cookie = `${trimmedName}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/api/auth;`;
  });

  window.location.href = "/";
}

// GTM/GA4 tracking — sends events via gtag() which is loaded by the GA4 Config tag in GTM.
// The gtag() stub (defined in base.html) queues events until gtag.js loads.
function trackEvent(eventName, params) {
  if (typeof gtag === "function") {
    gtag("event", eventName, params);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // Track outbound link clicks (GitHub, Udemy, portfolio, etc.)
  document.querySelectorAll('a[target="_blank"]').forEach((link) => {
    link.addEventListener("click", () => {
      const href = link.getAttribute("href") || "";
      const text = (link.textContent || "").trim().substring(0, 100);
      trackEvent("outbound_click", { link_url: href, link_text: text });
    });
  });

  // Track primary CTA clicks
  document
    .querySelectorAll('#get-started-btn, [href="#connect"]')
    .forEach((btn) => {
      btn.addEventListener("click", () => {
        trackEvent("cta_click", {
          cta_id: btn.id || "unknown",
          cta_text: (btn.textContent || "").trim(),
        });
      });
    });

  // Track CSV export file downloads
  document.querySelectorAll('a[href*="/export"]').forEach((link) => {
    link.addEventListener("click", () => {
      const href = link.getAttribute("href") || "";
      const fileName = href.split("/").pop() || "export.csv";
      trackEvent("file_download", {
        file_name: fileName,
        file_extension: "csv",
      });
    });
  });

  // Track scroll depth (25%, 50%, 75%, 100%)
  const scrollThresholds = [25, 50, 75, 100];
  const scrollReached = new Set();
  function checkScrollDepth() {
    const scrollTop = window.scrollY || document.documentElement.scrollTop;
    const docHeight =
      document.documentElement.scrollHeight -
      document.documentElement.clientHeight;
    if (docHeight <= 0) return;
    const percent = Math.round((scrollTop / docHeight) * 100);
    for (const threshold of scrollThresholds) {
      if (percent >= threshold && !scrollReached.has(threshold)) {
        scrollReached.add(threshold);
        trackEvent("scroll_depth", { percent_scrolled: threshold });
      }
    }
  }
  window.addEventListener("scroll", checkScrollDepth, { passive: true });
});

// Highlight active nav link
document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname;
  document.querySelectorAll(".nav-link").forEach((link) => {
    const href = link.getAttribute("href");
    if (href === path || (href === "/" && path === "/")) {
      link.classList.add("active");
    }
  });
});

// Toast notification utility
function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = "toast";

  // Set colors inline to avoid specificity conflicts and ensure premium light theme aesthetics
  const themes = {
    success: {
      bg: "#ECFDF5",
      border: "#A7F3D0",
      text: "#065F46",
      icon: "check-circle",
    },
    error: {
      bg: "#FEF2F2",
      border: "#FCA5A5",
      text: "#991B1B",
      icon: "alert-circle",
    },
    info: { bg: "#EFF6FF", border: "#BFDBFE", text: "#1E40AF", icon: "info" },
    warning: {
      bg: "#FFFBEB",
      border: "#FDE68A",
      text: "#92400E",
      icon: "alert-triangle",
    },
  };

  const theme = themes[type] || themes.info;
  toast.style.backgroundColor = theme.bg;
  toast.style.borderColor = theme.border;
  toast.style.color = theme.text;
  toast.style.borderStyle = "solid";
  toast.style.borderWidth = "1px";

  // Add Lucide icon
  const iconSpan = document.createElement("span");
  iconSpan.style.display = "inline-flex";
  iconSpan.style.alignItems = "center";

  const iconElement = document.createElement("i");
  iconElement.setAttribute("data-lucide", theme.icon);
  iconElement.style.width = "16px";
  iconElement.style.height = "16px";
  iconSpan.appendChild(iconElement);

  toast.appendChild(iconSpan);

  const textSpan = document.createElement("span");
  textSpan.textContent = message;
  toast.appendChild(textSpan);

  document.body.appendChild(toast);

  if (window.lucide) {
    lucide.createIcons({
      attrs: {
        class: "lucide-icon",
      },
      nameAttr: "data-lucide",
    });
  }

  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}
