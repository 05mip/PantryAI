let pantryItems = [];
let editingId = null;

const listEl = document.getElementById("pantry-list");
const searchEl = document.getElementById("pantry-search");
const addForm = document.getElementById("add-form");
const toggleBtn = document.getElementById("toggle-add-form");

toggleBtn.addEventListener("click", () => {
    addForm.classList.toggle("open");
    if (addForm.classList.contains("open")) {
        document.getElementById("add-name").focus();
    }
});

document.getElementById("add-item-btn").addEventListener("click", addItem);
document.getElementById("add-name").addEventListener("keydown", (e) => {
    if (e.key === "Enter") addItem();
});
searchEl.addEventListener("input", renderPantry);

async function loadPantry() {
    showSkeletonLines(listEl, 6);
    try {
        const resp = await apiFetch("/api/pantry");
        pantryItems = resp.data || [];
        renderPantry();
        updateBadges();
    } catch (err) {
        listEl.innerHTML = `<p style="color:var(--danger)">Failed to load pantry: ${escapeHtml(err.message)}</p>`;
    }
}

async function addItem() {
    const name = document.getElementById("add-name").value.trim();
    if (!name) return;

    const payload = {
        name,
        quantity: parseFloat(document.getElementById("add-qty").value) || 1,
        unit: document.getElementById("add-unit").value,
        category: document.getElementById("add-category").value,
    };
    const expiry = document.getElementById("add-expiry").value;
    if (expiry) payload.expiry_date = expiry;

    pantryItems.push({ ...payload, item_id: "temp-" + Date.now(), name: name.toLowerCase() });
    renderPantry();

    try {
        const resp = await apiFetch("/api/pantry", { method: "POST", body: payload });
        await loadPantry();
        document.getElementById("add-name").value = "";
        document.getElementById("add-qty").value = "1";
        document.getElementById("add-expiry").value = "";
        showToast("Item added to pantry");
    } catch (err) {
        showToast(err.message, "error");
        await loadPantry();
    }
}

async function deleteItem(itemId) {
    pantryItems = pantryItems.filter(i => i.item_id !== itemId);
    renderPantry();
    try {
        await apiFetch(`/api/pantry/${itemId}`, { method: "DELETE" });
        updateBadges();
        showToast("Item removed");
    } catch (err) {
        showToast(err.message, "error");
        await loadPantry();
    }
}

function startEdit(itemId) {
    editingId = itemId;
    renderPantry();
}

async function saveEdit(itemId) {
    const qtyInput = document.getElementById(`edit-qty-${itemId}`);
    const unitInput = document.getElementById(`edit-unit-${itemId}`);
    if (!qtyInput) return;

    try {
        await apiFetch(`/api/pantry/${itemId}`, {
            method: "PUT",
            body: { quantity: parseFloat(qtyInput.value) || 1, unit: unitInput.value },
        });
        editingId = null;
        await loadPantry();
        showToast("Item updated");
    } catch (err) {
        showToast(err.message, "error");
    }
}

function cancelEdit() {
    editingId = null;
    renderPantry();
}

function getExpiryInfo(dateStr) {
    if (!dateStr) return null;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const exp = new Date(dateStr + "T00:00:00");
    const diff = Math.ceil((exp - today) / (1000 * 60 * 60 * 24));
    if (diff < 0) return { text: "Expired", cls: "expiry-danger" };
    if (diff === 0) return { text: "Expires today", cls: "expiry-danger" };
    if (diff <= 3) return { text: `Expires in ${diff}d`, cls: "expiry-warn" };
    if (diff <= 7) return { text: `Expires in ${diff}d`, cls: "expiry-ok" };
    return { text: exp.toLocaleDateString(), cls: "" };
}

function renderPantry() {
    const query = searchEl.value.toLowerCase().trim();
    const filtered = query
        ? pantryItems.filter(i => i.name.toLowerCase().includes(query))
        : pantryItems;

    const groups = {};
    for (const item of filtered) {
        const cat = item.category || "other";
        if (!groups[cat]) groups[cat] = [];
        groups[cat].push(item);
    }

    const cats = Object.keys(groups).sort();
    if (cats.length === 0) {
        listEl.innerHTML = pantryItems.length === 0
            ? '<p style="color:var(--text-secondary); text-align:center; padding:40px;">Your pantry is empty. Add some items to get started!</p>'
            : '<p style="color:var(--text-secondary); text-align:center; padding:20px;">No items match your search.</p>';
        return;
    }

    let html = "";
    for (const cat of cats) {
        html += `<div class="category-section">`;
        html += `<div class="category-header" onclick="this.classList.toggle('collapsed')">
            <svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            ${escapeHtml(cat.charAt(0).toUpperCase() + cat.slice(1))} (${groups[cat].length})
        </div>`;
        html += `<div class="category-items">`;

        for (const item of groups[cat]) {
            const expiry = getExpiryInfo(item.expiry_date);
            const isEditing = editingId === item.item_id;

            html += `<div class="pantry-item" ${!isEditing ? `onclick="startEdit('${item.item_id}')"` : ""}>`;
            html += `<span class="item-name">${escapeHtml(item.name)}</span>`;

            if (isEditing) {
                html += `<div class="inline-edit">
                    <input type="number" id="edit-qty-${item.item_id}" value="${item.quantity}" min="0" step="any">
                    <select id="edit-unit-${item.item_id}">
                        ${["count","g","kg","ml","L","oz","lb","cups","tbsp","tsp"].map(u =>
                            `<option value="${u}" ${item.unit === u ? "selected" : ""}>${u}</option>`
                        ).join("")}
                    </select>
                    <button class="btn btn-primary btn-sm" onclick="event.stopPropagation(); saveEdit('${item.item_id}')">Save</button>
                    <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); cancelEdit()">Cancel</button>
                </div>`;
            } else {
                html += `<span class="item-qty">${item.quantity} ${escapeHtml(item.unit || "")}</span>`;
            }

            if (expiry) {
                html += `<span class="item-expiry ${expiry.cls}">${expiry.text}</span>`;
            }
            html += `<div class="item-actions">
                <button class="btn-icon" onclick="event.stopPropagation(); deleteItem('${item.item_id}')" title="Delete">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                </button>
            </div>`;
            html += `</div>`;
        }
        html += `</div></div>`;
    }
    listEl.innerHTML = html;
}

loadPantry();
