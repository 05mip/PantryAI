let groceryItems = [];
let suggestionsLoaded = false;

const listEl = document.getElementById("grocery-list");
const suggestionsBody = document.getElementById("suggestions-body");

document.getElementById("add-grocery-btn").addEventListener("click", addItem);
document.getElementById("grocery-name").addEventListener("keydown", e => {
    if (e.key === "Enter") addItem();
});
document.getElementById("clear-checked-btn").addEventListener("click", clearChecked);
document.getElementById("to-pantry-btn").addEventListener("click", toPantry);
document.getElementById("suggestions-toggle").addEventListener("click", toggleSuggestions);

async function loadGrocery() {
    showSkeletonLines(listEl, 5);
    try {
        const resp = await apiFetch("/api/grocery");
        groceryItems = resp.data || [];
        renderGrocery();
        updateBadges();
    } catch (err) {
        listEl.innerHTML = `<p style="color:var(--danger)">Failed to load grocery list: ${escapeHtml(err.message)}</p>`;
    }
}

async function addItem() {
    const name = document.getElementById("grocery-name").value.trim();
    if (!name) return;
    const payload = {
        name,
        quantity: parseFloat(document.getElementById("grocery-qty").value) || 1,
        unit: document.getElementById("grocery-unit").value,
        source: "manual",
    };

    try {
        await apiFetch("/api/grocery", { method: "POST", body: payload });
        document.getElementById("grocery-name").value = "";
        document.getElementById("grocery-qty").value = "1";
        await loadGrocery();
        showToast("Item added to grocery list");
    } catch (err) {
        showToast(err.message, "error");
    }
}

async function toggleCheck(itemId, checked) {
    try {
        await apiFetch(`/api/grocery/${itemId}`, { method: "PUT", body: { checked } });
        await loadGrocery();
    } catch (err) {
        showToast(err.message, "error");
    }
}

async function deleteItem(itemId) {
    try {
        await apiFetch(`/api/grocery/${itemId}`, { method: "DELETE" });
        await loadGrocery();
        showToast("Item removed");
    } catch (err) {
        showToast(err.message, "error");
    }
}

async function clearChecked() {
    try {
        const resp = await apiFetch("/api/grocery/checked", { method: "DELETE" });
        await loadGrocery();
        showToast(`${resp.data.cleared} checked items cleared`);
    } catch (err) {
        showToast(err.message, "error");
    }
}

async function toPantry() {
    const checkedCount = groceryItems.filter(i => i.checked).length;
    if (checkedCount === 0) {
        showToast("No checked items to move", "error");
        return;
    }
    try {
        const resp = await apiFetch("/api/grocery/to-pantry", { method: "POST" });
        await loadGrocery();
        showToast(`${resp.data.moved} items added to your pantry`);
        updateBadges();
    } catch (err) {
        showToast(err.message, "error");
    }
}

function renderGrocery() {
    if (groceryItems.length === 0) {
        listEl.innerHTML = '<p style="color:var(--text-secondary); text-align:center; padding:40px;">Your grocery list is empty.</p>';
        return;
    }

    let html = "";
    for (const item of groceryItems) {
        const checkedCls = item.checked ? "checked" : "";
        html += `<div class="grocery-item ${checkedCls}">
            <input type="checkbox" ${item.checked ? "checked" : ""} onchange="toggleCheck('${item.item_id}', this.checked)">
            <span class="grocery-name">${escapeHtml(item.name)}</span>
            <span class="grocery-qty">${item.quantity} ${escapeHtml(item.unit || "")}</span>`;
        if (item.source && item.source !== "manual") {
            html += `<span class="pill pill-source">${escapeHtml(item.source)}</span>`;
        }
        html += `<button class="btn-icon" onclick="deleteItem('${item.item_id}')" title="Delete">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
        </div>`;
    }
    listEl.innerHTML = html;
}

async function toggleSuggestions() {
    const body = suggestionsBody;
    if (body.classList.contains("open")) {
        body.classList.remove("open");
        return;
    }
    body.classList.add("open");
    if (suggestionsLoaded) return;

    showSkeletonLines(body, 4);
    try {
        const resp = await apiFetch("/api/recipes/smart-suggestions");
        const suggestions = resp.data || [];
        suggestionsLoaded = true;
        if (suggestions.length === 0) {
            body.innerHTML = '<p style="color:var(--text-secondary); padding:12px;">No suggestions available. Add more items to your pantry first.</p>';
            return;
        }
        let html = "";
        for (const s of suggestions) {
            html += `<div class="suggestion-item">
                <div class="item-name">${escapeHtml(s.item)}</div>
                <div class="unlocks">Unlocks: ${(s.unlocks_recipes || []).map(r => escapeHtml(r)).join(", ")}</div>
            </div>`;
        }
        body.innerHTML = html;
    } catch (err) {
        body.innerHTML = `<p style="color:var(--danger); padding:12px;">Failed to load suggestions: ${escapeHtml(err.message)}</p>`;
    }
}

loadGrocery();
