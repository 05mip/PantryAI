const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MEALS = ["breakfast", "lunch", "dinner"];
const MEAL_LABELS = { breakfast: "Breakfast", lunch: "Lunch", dinner: "Dinner" };

let currentWeekOffset = 0;
let mealData = null;
let searchingSlot = null;
let searchTimeout = null;

const gridEl = document.getElementById("meal-grid");
const weekLabel = document.getElementById("week-label");
const previewResults = document.getElementById("preview-results");

document.getElementById("prev-week").addEventListener("click", () => {
    currentWeekOffset--;
    loadMeals();
});
document.getElementById("next-week").addEventListener("click", () => {
    currentWeekOffset++;
    loadMeals();
});
document.getElementById("preview-btn").addEventListener("click", loadPreview);

function getWeekString(offset) {
    const d = new Date();
    d.setDate(d.getDate() + offset * 7);
    const year = d.getFullYear();
    const jan4 = new Date(year, 0, 4);
    const daysSinceJan4 = Math.floor((d - jan4) / (86400000));
    const weekNum = Math.ceil((daysSinceJan4 + jan4.getDay() + 1) / 7);
    const padded = String(Math.max(1, Math.min(weekNum, 53))).padStart(2, "0");
    return `${year}-${padded}`;
}

async function loadMeals() {
    const week = getWeekString(currentWeekOffset);
    showSkeletonLines(gridEl, 3);
    try {
        const resp = await apiFetch(`/api/meals?week=${week}`);
        mealData = resp.data;
        weekLabel.textContent = `Week of ${mealData.start_date} – ${mealData.end_date}`;
        renderGrid();
    } catch (err) {
        gridEl.innerHTML = `<p style="color:var(--danger)">Failed to load meals: ${escapeHtml(err.message)}</p>`;
    }
}

function getTodayDayName() {
    const names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    return names[new Date().getDay()];
}

function renderGrid() {
    if (!mealData) return;
    const g = mealData.grid;
    const today = currentWeekOffset === 0 ? getTodayDayName() : null;
    let html = "";

    html += `<div></div>`;
    for (const day of DAYS) {
        const info = g[day] || {};
        const isToday = day === today;
        html += `<div class="day-header${isToday ? " today" : ""}">${day}<span class="date">${info.display_date || ""}</span></div>`;
    }

    for (const meal of MEALS) {
        html += `<div class="meal-label">${MEAL_LABELS[meal]}</div>`;
        for (const day of DAYS) {
            const info = g[day] || {};
            const slot = info.meals ? info.meals[meal] : null;
            const slotId = `${mealData.week}-${day}-${meal}`;
            const isSearching = searchingSlot === slotId;
            const isToday = day === today;

            html += `<div class="meal-cell${isToday ? " today" : ""}" id="cell-${slotId}" onclick="cellClick('${slotId}')">`;
            if (isSearching) {
                html += `<div class="meal-search">
                    <input type="text" id="search-${slotId}" placeholder="Search..." oninput="onMealSearch(event, '${slotId}')" onclick="event.stopPropagation()">
                    <div class="meal-search-results" id="results-${slotId}"></div>
                </div>`;
            } else if (slot) {
                html += `<div class="meal-info">
                    <div class="meal-title">${escapeHtml(slot.recipe_title || "")}</div>
                    <div class="meal-servings">
                        <input type="number" class="servings-input" value="${slot.servings || 1}" min="1"
                            onclick="event.stopPropagation()"
                            onchange="updateServings('${slotId}', '${slot.recipe_id}', '${escapeHtml(slot.recipe_title || "")}', this.value)">
                        servings
                    </div>
                </div>
                <button class="clear-btn" onclick="event.stopPropagation(); clearSlot('${slotId}')">&times;</button>`;
            } else {
                html += `<span class="add-meal">+ Add meal</span>`;
            }
            html += `</div>`;
        }
    }

    gridEl.innerHTML = html;

    if (searchingSlot) {
        const input = document.getElementById(`search-${searchingSlot}`);
        if (input) input.focus();
    }
}

function cellClick(slotId) {
    if (searchingSlot === slotId) return;
    searchingSlot = slotId;
    renderGrid();
}

function positionDropdown(slotId) {
    const input = document.getElementById(`search-${slotId}`);
    const resultsEl = document.getElementById(`results-${slotId}`);
    if (!input || !resultsEl) return;
    const rect = input.getBoundingClientRect();
    resultsEl.style.left = rect.left + "px";
    resultsEl.style.top = (rect.bottom + 2) + "px";
    resultsEl.style.width = Math.max(rect.width, 200) + "px";
}

function onMealSearch(event, slotId) {
    clearTimeout(searchTimeout);
    const q = event.target.value.trim();
    const resultsEl = document.getElementById(`results-${slotId}`);
    if (q.length < 2) {
        resultsEl.innerHTML = "";
        return;
    }
    positionDropdown(slotId);
    searchTimeout = setTimeout(async () => {
        try {
            const resp = await apiFetch(`/api/recipes/search?q=${encodeURIComponent(q)}&limit=8`);
            const recipes = resp.data || [];
            if (recipes.length === 0) {
                resultsEl.innerHTML = '<div class="result-item" style="color:var(--text-secondary)">No recipes found</div>';
                positionDropdown(slotId);
                return;
            }
            resultsEl.innerHTML = recipes.map(r =>
                `<div class="result-item" onclick="event.stopPropagation(); selectRecipe('${slotId}', '${r.recipe_id}', '${escapeHtml(r.title || "").replace(/'/g, "\\'")}')">${escapeHtml(r.title || "")}</div>`
            ).join("");
            positionDropdown(slotId);
        } catch (err) {
            resultsEl.innerHTML = `<div class="result-item" style="color:var(--danger)">Search failed</div>`;
        }
    }, 300);
}

async function selectRecipe(slotId, recipeId, title) {
    searchingSlot = null;
    try {
        await apiFetch(`/api/meals/${slotId}`, {
            method: "PUT",
            body: { recipe_id: recipeId, servings: 1 },
        });
        await loadMeals();
        showToast(`Added "${title}" to meal plan`);
    } catch (err) {
        showToast(err.message, "error");
    }
}

async function updateServings(slotId, recipeId, title, servings) {
    try {
        await apiFetch(`/api/meals/${slotId}`, {
            method: "PUT",
            body: { recipe_id: recipeId, servings: parseInt(servings) || 1 },
        });
    } catch (err) {
        showToast(err.message, "error");
    }
}

async function clearSlot(slotId) {
    try {
        await apiFetch(`/api/meals/${slotId}`, { method: "DELETE" });
        const parts = slotId.split("-");
        if (parts.length >= 4 && mealData) {
            const day = parts[2];
            const meal = parts[3];
            if (mealData.grid[day] && mealData.grid[day].meals) {
                mealData.grid[day].meals[meal] = null;
            }
        }
        renderGrid();
    } catch (err) {
        showToast(err.message, "error");
    }
}

async function loadPreview() {
    const week = getWeekString(currentWeekOffset);
    previewResults.innerHTML = "";
    showSkeletonLines(previewResults, 5);

    try {
        const resp = await apiFetch(`/api/meals/grocery-preview?week=${week}`);
        const data = resp.data;
        let html = "";

        if (data.have_none.length > 0) {
            html += renderPreviewSection("Need to buy", "dot-red", data.have_none, true);
        }
        if (data.have_partial.length > 0) {
            html += renderPreviewSection("Buy more", "dot-yellow", data.have_partial, true);
        }
        if (data.have_enough.length > 0) {
            html += renderPreviewSection("Already have", "dot-green", data.have_enough, false);
        }

        if (!data.have_none.length && !data.have_partial.length && !data.have_enough.length) {
            html = '<p style="color:var(--text-secondary); padding:12px;">No meals planned for this week.</p>';
        } else {
            html += `<button class="btn btn-primary" style="margin-top:16px" onclick="addAllToGrocery()">Add all to grocery list</button>`;
        }

        previewResults.innerHTML = html;
    } catch (err) {
        previewResults.innerHTML = `<p style="color:var(--danger)">Failed to load preview: ${escapeHtml(err.message)}</p>`;
    }
}

function renderPreviewSection(title, dotCls, items, startOpen) {
    const id = title.replace(/\s/g, "-").toLowerCase();
    let html = `<div class="preview-section">
        <div class="preview-section-header" onclick="document.getElementById('ps-${id}').style.display = document.getElementById('ps-${id}').style.display === 'none' ? 'block' : 'none'">
            <span class="status-dot ${dotCls}"></span> ${title} (${items.length})
        </div>
        <div id="ps-${id}" style="display:${startOpen ? "block" : "none"}">`;
    for (const item of items) {
        html += `<div class="preview-item">
            <span class="name">${escapeHtml(item.name)}</span>
            <span class="qty">Need: ${item.needed} ${escapeHtml(item.unit || "")}`;
        if (item.on_hand > 0) html += ` (have: ${item.on_hand})`;
        if (item.short) html += ` — short ${item.short}`;
        html += `</span></div>`;
    }
    html += `</div></div>`;
    return html;
}

async function addAllToGrocery() {
    const week = getWeekString(currentWeekOffset);
    try {
        const resp = await apiFetch("/api/grocery/from-meal-plan", {
            method: "POST",
            body: { week },
        });
        const d = resp.data;
        showToast(`${d.added} items added, ${d.already_in_stock} in stock, ${d.already_on_list} already on list`);
        updateBadges();
    } catch (err) {
        showToast(err.message, "error");
    }
}

document.addEventListener("click", (e) => {
    if (searchingSlot && !e.target.closest(".meal-cell")) {
        searchingSlot = null;
        renderGrid();
    }
});

document.addEventListener("scroll", () => {
    if (searchingSlot) positionDropdown(searchingSlot);
}, true);

loadMeals();
