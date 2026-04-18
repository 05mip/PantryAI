async function apiFetch(path, options = {}) {
    const defaults = {
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
    };
    const merged = { ...defaults, ...options };
    if (options.headers) {
        merged.headers = { ...defaults.headers, ...options.headers };
    }
    if (merged.body && typeof merged.body === "object" && !(merged.body instanceof FormData)) {
        merged.body = JSON.stringify(merged.body);
    }

    try {
        const resp = await fetch(path, merged);
        const data = await resp.json();
        if (!resp.ok || !data.success) {
            throw new Error(data.error || `Request failed (${resp.status})`);
        }
        return data;
    } catch (err) {
        throw err;
    }
}

function showToast(message, type = "success") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function showSkeleton(container, count = 3) {
    container.innerHTML = "";
    for (let i = 0; i < count; i++) {
        const el = document.createElement("div");
        el.className = "skeleton skeleton-card";
        container.appendChild(el);
    }
}

function showSkeletonLines(container, count = 5) {
    container.innerHTML = "";
    for (let i = 0; i < count; i++) {
        const el = document.createElement("div");
        const widths = ["w75", "w50", "w30"];
        el.className = `skeleton skeleton-line ${widths[i % 3]}`;
        container.appendChild(el);
    }
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

async function updateBadges() {
    try {
        const pantryResp = await fetch("/api/pantry", { credentials: "same-origin" });
        if (pantryResp.ok) {
            const pd = await pantryResp.json();
            const badge = document.getElementById("pantry-badge");
            if (badge && pd.data) {
                badge.textContent = pd.data.length;
                badge.style.display = pd.data.length > 0 ? "inline-flex" : "none";
            }
        }
    } catch (e) { /* ignore */ }

    try {
        const groceryResp = await fetch("/api/grocery", { credentials: "same-origin" });
        if (groceryResp.ok) {
            const gd = await groceryResp.json();
            const badge = document.getElementById("grocery-badge");
            if (badge && gd.data) {
                const unchecked = gd.data.filter(i => !i.checked).length;
                badge.textContent = unchecked;
                badge.style.display = unchecked > 0 ? "inline-flex" : "none";
            }
        }
    } catch (e) { /* ignore */ }
}

document.addEventListener("DOMContentLoaded", () => {
    updateBadges();
});
