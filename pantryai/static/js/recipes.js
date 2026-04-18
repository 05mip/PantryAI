let currentTab = "matches";
let allRecipes = [];
let searchTimeout = null;
let expandedId = null;

const grid = document.getElementById("recipe-grid");
const searchInput = document.getElementById("recipe-search");
const cuisineSelect = document.getElementById("filter-cuisine");
const missingWrap = document.getElementById("filter-missing-wrap");
const missingSlider = document.getElementById("filter-missing");
const missingVal = document.getElementById("missing-val");
const favsCheck = document.getElementById("filter-favs");

document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        currentTab = tab.dataset.tab;
        missingWrap.style.display = currentTab === "near" ? "flex" : "none";
        searchInput.value = "";
        loadRecipes();
    });
});

missingSlider.addEventListener("input", () => {
    missingVal.textContent = missingSlider.value;
    loadRecipes();
});
favsCheck.addEventListener("change", renderRecipes);
cuisineSelect.addEventListener("change", renderRecipes);

searchInput.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    const q = searchInput.value.trim();
    if (q.length === 0) {
        loadRecipes();
        return;
    }
    searchTimeout = setTimeout(() => searchRecipes(q), 300);
});

async function loadRecipes() {
    showSkeleton(grid, 6);
    try {
        let url;
        if (currentTab === "matches") {
            url = "/api/recipes/matches";
        } else {
            url = `/api/recipes/near-matches?max_missing=${missingSlider.value}`;
        }
        const resp = await apiFetch(url);
        allRecipes = resp.data || [];
        populateCuisines();
        renderRecipes();
    } catch (err) {
        grid.innerHTML = `<p style="color:var(--danger)">Failed to load recipes: ${escapeHtml(err.message)}</p>`;
    }
}

async function searchRecipes(query) {
    showSkeleton(grid, 4);
    try {
        const resp = await apiFetch(`/api/recipes/search?q=${encodeURIComponent(query)}`);
        allRecipes = resp.data || [];
        renderRecipes();
    } catch (err) {
        grid.innerHTML = `<p style="color:var(--danger)">Search failed: ${escapeHtml(err.message)}</p>`;
    }
}

function populateCuisines() {
    const cuisines = new Set(allRecipes.map(r => r.cuisine).filter(Boolean));
    const current = cuisineSelect.value;
    cuisineSelect.innerHTML = '<option value="">All</option>';
    for (const c of [...cuisines].sort()) {
        const opt = document.createElement("option");
        opt.value = c;
        opt.textContent = c;
        cuisineSelect.appendChild(opt);
    }
    cuisineSelect.value = current;
}

function renderRecipes() {
    let recipes = [...allRecipes];
    const cuisine = cuisineSelect.value;
    if (cuisine) {
        recipes = recipes.filter(r => r.cuisine === cuisine);
    }
    if (favsCheck.checked) {
        recipes.sort((a, b) => (b.is_favorite ? 1 : 0) - (a.is_favorite ? 1 : 0));
    }

    if (recipes.length === 0) {
        grid.innerHTML = '<p style="color:var(--text-secondary); text-align:center; padding:40px; grid-column: 1/-1;">No recipes found. Try adjusting your filters or adding more items to your pantry.</p>';
        return;
    }

    grid.innerHTML = recipes.map(r => recipeCard(r)).join("");
}

function recipeCard(r) {
    const score = r.match_score != null ? r.match_score : 0;
    const scoreCls = score >= 70 ? "score-high" : score >= 40 ? "score-med" : "score-low";
    const heartCls = r.is_favorite ? "favorited" : "";
    const missing = r.missing_ingredients || [];
    const isExpanded = expandedId === r.recipe_id;

    let html = `<div class="recipe-card" id="card-${r.recipe_id}">`;
    html += `<div class="recipe-card-header">
        <h3>${escapeHtml(r.title || "Untitled")}</h3>
        <button class="heart-btn ${heartCls}" onclick="event.stopPropagation(); toggleFav('${r.recipe_id}')" title="Favorite">
            ${r.is_favorite ? "&#10084;" : "&#9825;"}
        </button>
    </div>`;

    html += `<div class="recipe-card-body" onclick="toggleExpand('${r.recipe_id}')">`;
    if (r.cuisine) {
        html += `<span class="pill pill-cuisine">${escapeHtml(r.cuisine)}</span> `;
    }
    if (r.match_score != null) {
        html += `<div class="score-bar"><div class="score-bar-fill ${scoreCls}" style="width:${score}%"></div></div>`;
        html += `<div class="score-label">${score}% match</div>`;
    }
    if (missing.length > 0) {
        html += `<div class="pills-row">`;
        for (const m of missing.slice(0, 5)) {
            html += `<span class="pill pill-missing">${escapeHtml(m.name || "")}</span>`;
        }
        if (missing.length > 5) html += `<span class="pill pill-missing">+${missing.length - 5} more</span>`;
        html += `</div>`;
    }
    if (missing.length > 0) {
        html += `<button class="btn btn-secondary btn-sm" style="margin-top:8px" onclick="event.stopPropagation(); addMissing('${r.recipe_id}')">Add missing to list</button>`;
    }
    html += `</div>`;

    html += `<div class="recipe-detail ${isExpanded ? 'open' : ''}" id="detail-${r.recipe_id}">`;
    if (r.ingredients && r.ingredients.length) {
        html += `<h4>Ingredients</h4><ul>`;
        for (const ing of r.ingredients) {
            html += `<li>${ing.quantity || ""} ${escapeHtml(ing.unit || "")} ${escapeHtml(ing.name || "")}</li>`;
        }
        html += `</ul>`;
    }
    if (r.instructions) {
        html += `<h4>Instructions</h4><div class="instructions">${escapeHtml(r.instructions)}</div>`;
    }
    if (r.prep_time_mins) {
        html += `<p style="margin-top:8px; font-size:0.85rem; color:var(--text-secondary)">Prep: ${r.prep_time_mins} min | Serves: ${r.servings || "?"}</p>`;
    }
    html += `</div>`;
    html += `</div>`;
    return html;
}

function toggleExpand(recipeId) {
    expandedId = expandedId === recipeId ? null : recipeId;
    const detail = document.getElementById(`detail-${recipeId}`);
    if (detail) detail.classList.toggle("open");
}

async function toggleFav(recipeId) {
    try {
        const resp = await apiFetch(`/api/recipes/${recipeId}/favorite`, { method: "POST" });
        const recipe = allRecipes.find(r => r.recipe_id === recipeId);
        if (recipe) recipe.is_favorite = resp.data.is_favorite;
        renderRecipes();
    } catch (err) {
        showToast(err.message, "error");
    }
}

async function addMissing(recipeId) {
    try {
        const resp = await apiFetch(`/api/grocery/from-recipe/${recipeId}`, { method: "POST" });
        showToast(`${resp.data.added} items added to grocery list`);
        updateBadges();
    } catch (err) {
        showToast(err.message, "error");
    }
}

loadRecipes();
