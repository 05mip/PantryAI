(function () {
    const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const MEALS = ["breakfast", "lunch", "dinner"];

    let conversationId = null;
    let sending = false;

    const examplePrompts = [
        "I'm bulking this week — plan my meals",
        "What can I make with what's in my pantry?",
        "I'm out of heavy cream — what can I substitute?",
        "Make a recipe for marry me chicken",
        "I want to eat healthy this week under 2000 calories/day",
        "Add chicken, rice, and broccoli to my grocery list",
    ];

    function getISOWeek() {
        const now = new Date();
        const d = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
        const dayNum = d.getUTCDay() || 7;
        d.setUTCDate(d.getUTCDate() + 4 - dayNum);
        const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
        const weekNo = Math.ceil(((d - yearStart) / 86400000 + 1) / 7);
        return `${d.getUTCFullYear()}-${String(weekNo).padStart(2, "0")}`;
    }

    function init() {
        const fab = document.getElementById("chat-fab");
        const panel = document.getElementById("chat-panel");
        const closeBtn = document.getElementById("chat-close");
        const form = document.getElementById("chat-form");
        const input = document.getElementById("chat-input");

        fab.addEventListener("click", () => {
            panel.classList.toggle("open");
            fab.classList.remove("has-unread");
            if (panel.classList.contains("open")) {
                input.focus();
            }
        });

        closeBtn.addEventListener("click", () => {
            panel.classList.remove("open");
        });

        form.addEventListener("submit", (e) => {
            e.preventDefault();
            const msg = input.value.trim();
            if (!msg || sending) return;
            input.value = "";
            sendMessage(msg);
        });

        renderWelcome();
    }

    function renderWelcome() {
        const messages = document.getElementById("chat-messages");
        messages.innerHTML = "";

        const welcome = document.createElement("div");
        welcome.className = "chat-welcome";
        welcome.innerHTML = `
            <div class="chat-welcome-icon">👨‍🍳</div>
            <h3>Hi! I'm Chef Charlie</h3>
            <p>Your personal kitchen assistant. I can help with meal planning, recipes, grocery lists, and more. Try one of these:</p>
            <div class="chat-chips"></div>
        `;

        const chips = welcome.querySelector(".chat-chips");
        examplePrompts.forEach((prompt) => {
            const chip = document.createElement("button");
            chip.className = "chat-chip";
            chip.textContent = prompt;
            chip.addEventListener("click", () => {
                sendMessage(prompt);
            });
            chips.appendChild(chip);
        });

        messages.appendChild(welcome);
    }

    function addBubble(role, contentHtml) {
        const messages = document.getElementById("chat-messages");
        const welcome = messages.querySelector(".chat-welcome");
        if (welcome) welcome.remove();

        const bubble = document.createElement("div");
        bubble.className = `chat-bubble chat-${role}`;
        bubble.innerHTML = contentHtml;
        messages.appendChild(bubble);
        messages.scrollTop = messages.scrollHeight;
        return bubble;
    }

    function showTyping() {
        const messages = document.getElementById("chat-messages");
        const el = document.createElement("div");
        el.className = "chat-bubble chat-assistant chat-typing";
        el.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
        el.id = "chat-typing-indicator";
        messages.appendChild(el);
        messages.scrollTop = messages.scrollHeight;
    }

    function hideTyping() {
        const el = document.getElementById("chat-typing-indicator");
        if (el) el.remove();
    }

    async function sendMessage(text) {
        if (sending) return;
        sending = true;
        const input = document.getElementById("chat-input");
        const sendBtn = document.getElementById("chat-send");
        input.disabled = true;
        sendBtn.disabled = true;

        addBubble("user", escapeHtml(text));
        showTyping();

        try {
            const resp = await apiFetch("/api/chat", {
                method: "POST",
                body: { message: text, conversation_id: conversationId },
            });
            hideTyping();
            const data = resp.data;
            conversationId = data.conversation_id;
            renderBlocks(data.blocks);

            const panel = document.getElementById("chat-panel");
            if (!panel.classList.contains("open")) {
                document.getElementById("chat-fab").classList.add("has-unread");
            }
        } catch (err) {
            hideTyping();
            addBubble("assistant", "Sorry, something went wrong. Please try again.");
        } finally {
            sending = false;
            input.disabled = false;
            sendBtn.disabled = false;
            input.focus();
        }
    }

    function renderBlocks(blocks) {
        if (!blocks || !blocks.length) {
            addBubble("assistant", "I don't have a response right now. Try asking something else!");
            return;
        }
        blocks.forEach((block) => {
            switch (block.type) {
                case "text":
                    addBubble("assistant", formatText(block.content || ""));
                    break;
                case "meal_plan_proposal":
                    renderMealPlanProposal(block.data);
                    break;
                case "grocery_proposal":
                    renderGroceryProposal(block.data);
                    break;
                case "recipe_proposal":
                    renderRecipeProposal(block.data);
                    break;
                case "substitution":
                    renderSubstitution(block.data);
                    break;
                default:
                    if (block.content) {
                        addBubble("assistant", formatText(block.content));
                    }
            }
        });
    }

    function formatText(text) {
        return escapeHtml(text)
            .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
            .replace(/\n/g, "<br>");
    }

    // ── Meal Plan Proposal ──

    function renderMealPlanProposal(data) {
        const bubble = addBubble("assistant", "");
        const wrapper = document.createElement("div");
        wrapper.className = "chat-block meal-plan-block";

        let html = '<h4>📅 Proposed Meal Plan</h4><div class="mini-meal-grid">';
        html += '<div class="grid-header"><span></span>';
        MEALS.forEach((m) => (html += `<span>${m.charAt(0).toUpperCase() + m.slice(1)}</span>`));
        html += "</div>";

        DAYS.forEach((day) => {
            html += `<div class="grid-row"><span class="day-label">${day}</span>`;
            MEALS.forEach((meal) => {
                const slot = data[day] && data[day][meal];
                const title = slot ? slot.title || "—" : "—";
                html += `<span class="grid-cell" title="${escapeHtml(title)}">${escapeHtml(title)}</span>`;
            });
            html += "</div>";
        });
        html += "</div>";

        html += '<div class="chat-actions">';
        html += '<button class="btn-action btn-primary" data-action="fill-meal-plan">Fill out this week\'s meal plan</button>';
        html += '<button class="btn-action btn-secondary" data-action="dismiss">No thanks</button>';
        html += "</div>";

        wrapper.innerHTML = html;

        wrapper.querySelector('[data-action="fill-meal-plan"]').addEventListener("click", () => fillMealPlan(data, wrapper));
        wrapper.querySelector('[data-action="dismiss"]').addEventListener("click", () => {
            wrapper.querySelector(".chat-actions").innerHTML = '<span class="dismissed">Dismissed</span>';
        });

        bubble.innerHTML = "";
        bubble.appendChild(wrapper);
    }

    async function fillMealPlan(data, wrapper) {
        const actionsDiv = wrapper.querySelector(".chat-actions");
        actionsDiv.innerHTML = '<span class="action-loading">Filling meal plan...</span>';
        const week = getISOWeek();
        let filled = 0;
        let errors = 0;

        for (const day of DAYS) {
            if (!data[day]) continue;
            for (const meal of MEALS) {
                const slot = data[day][meal];
                if (!slot || !slot.title) continue;

                let recipeId = slot.recipe_id;
                if (!recipeId) {
                    try {
                        const created = await apiFetch("/api/recipes", {
                            method: "POST",
                            body: {
                                title: slot.title,
                                ingredients: slot.ingredients || [],
                                instructions: slot.instructions || "",
                                cuisine: slot.cuisine || "",
                                servings: slot.servings || 1,
                            },
                        });
                        recipeId = created.data.recipe_id;
                    } catch {
                        errors++;
                        continue;
                    }
                }

                const slotId = `${week}_${day}_${meal}`;
                try {
                    await apiFetch(`/api/meals/${slotId}`, {
                        method: "PUT",
                        body: { recipe_id: recipeId, servings: slot.servings || 1 },
                    });
                    filled++;
                } catch {
                    errors++;
                }
            }
        }

        actionsDiv.innerHTML = `<span class="action-done">✓ Filled ${filled} meal slots${errors ? `, ${errors} failed` : ""}</span>`;
        showToast(`Meal plan updated (${filled} slots)`, "success");
    }

    // ── Grocery Proposal ──

    function renderGroceryProposal(data) {
        const items = data.items || [];
        if (!items.length) return;

        const bubble = addBubble("assistant", "");
        const wrapper = document.createElement("div");
        wrapper.className = "chat-block grocery-block";

        let html = "<h4>🛒 Suggested Grocery Items</h4><ul class='grocery-check-list'>";
        items.forEach((item, i) => {
            const label = `${item.quantity || 1} ${item.unit || ""} ${item.name}`.trim();
            html += `<li><label><input type="checkbox" checked data-idx="${i}"> ${escapeHtml(label)}</label></li>`;
        });
        html += "</ul>";
        html += '<div class="chat-actions">';
        html += '<button class="btn-action btn-primary" data-action="add-grocery">Add to grocery list</button>';
        html += '<button class="btn-action btn-secondary" data-action="dismiss">Skip</button>';
        html += "</div>";

        wrapper.innerHTML = html;

        wrapper.querySelector('[data-action="add-grocery"]').addEventListener("click", () => addGroceryItems(items, wrapper));
        wrapper.querySelector('[data-action="dismiss"]').addEventListener("click", () => {
            wrapper.querySelector(".chat-actions").innerHTML = '<span class="dismissed">Skipped</span>';
        });

        bubble.innerHTML = "";
        bubble.appendChild(wrapper);
    }

    async function addGroceryItems(items, wrapper) {
        const actionsDiv = wrapper.querySelector(".chat-actions");
        const checkboxes = wrapper.querySelectorAll('input[type="checkbox"]');
        const selected = [];
        checkboxes.forEach((cb) => {
            if (cb.checked) selected.push(items[parseInt(cb.dataset.idx)]);
        });

        if (!selected.length) {
            actionsDiv.innerHTML = '<span class="dismissed">No items selected</span>';
            return;
        }

        actionsDiv.innerHTML = '<span class="action-loading">Adding items...</span>';
        let added = 0;
        for (const item of selected) {
            try {
                await apiFetch("/api/grocery", {
                    method: "POST",
                    body: { name: item.name, quantity: item.quantity || 1, unit: item.unit || "count", source: "chef_charlie" },
                });
                added++;
            } catch { /* continue */ }
        }
        actionsDiv.innerHTML = `<span class="action-done">✓ Added ${added} items to grocery list</span>`;
        showToast(`${added} items added to grocery list`, "success");
        updateBadges();
    }

    // ── Recipe Proposal ──

    function renderRecipeProposal(data) {
        const bubble = addBubble("assistant", "");
        const wrapper = document.createElement("div");
        wrapper.className = "chat-block recipe-block";

        const ings = (data.ingredients || []).map((i) => `${i.quantity || ""} ${i.unit || ""} ${i.name}`.trim());

        let html = `<h4>📖 ${escapeHtml(data.title || "New Recipe")}</h4>`;
        if (data.cuisine) html += `<span class="recipe-meta">${escapeHtml(data.cuisine)}</span>`;
        if (data.prep_time_mins) html += `<span class="recipe-meta"> · ${data.prep_time_mins} min</span>`;
        if (data.servings) html += `<span class="recipe-meta"> · ${data.servings} servings</span>`;

        html += "<div class='recipe-section'><strong>Ingredients:</strong><ul>";
        ings.forEach((i) => (html += `<li>${escapeHtml(i)}</li>`));
        html += "</ul></div>";

        if (data.instructions) {
            html += "<div class='recipe-section'><strong>Instructions:</strong><p>" +
                escapeHtml(data.instructions).replace(/\n/g, "<br>") + "</p></div>";
        }

        html += '<div class="chat-actions">';
        html += '<button class="btn-action btn-primary" data-action="save-recipe">Save this recipe</button>';
        html += '<button class="btn-action btn-secondary" data-action="dismiss">Dismiss</button>';
        html += "</div>";

        wrapper.innerHTML = html;

        wrapper.querySelector('[data-action="save-recipe"]').addEventListener("click", () => saveProposedRecipe(data, wrapper));
        wrapper.querySelector('[data-action="dismiss"]').addEventListener("click", () => {
            wrapper.querySelector(".chat-actions").innerHTML = '<span class="dismissed">Dismissed</span>';
        });

        bubble.innerHTML = "";
        bubble.appendChild(wrapper);
    }

    async function saveProposedRecipe(data, wrapper) {
        const actionsDiv = wrapper.querySelector(".chat-actions");
        actionsDiv.innerHTML = '<span class="action-loading">Saving recipe...</span>';

        try {
            await apiFetch("/api/recipes", {
                method: "POST",
                body: {
                    title: data.title,
                    cuisine: data.cuisine || "",
                    prep_time_mins: data.prep_time_mins || 0,
                    servings: data.servings || 4,
                    ingredients: data.ingredients || [],
                    instructions: data.instructions || "",
                },
            });
            actionsDiv.innerHTML = '<span class="action-done">✓ Recipe saved!</span>';
            showToast(`"${data.title}" saved to recipes`, "success");
        } catch {
            actionsDiv.innerHTML = '<span class="action-error">Failed to save — try again</span>';
        }
    }

    // ── Substitution ──

    function renderSubstitution(data) {
        const bubble = addBubble("assistant", "");
        const wrapper = document.createElement("div");
        wrapper.className = "chat-block substitution-block";

        let html = "<h4>🔄 Substitution</h4>";
        html += `<p><strong>${escapeHtml(data.original || "")}</strong> → <strong>${escapeHtml(data.substitute || "")}</strong></p>`;
        if (data.ratio) html += `<p class="sub-detail">Ratio: ${escapeHtml(data.ratio)}</p>`;
        if (data.notes) html += `<p class="sub-detail">${escapeHtml(data.notes)}</p>`;

        wrapper.innerHTML = html;
        bubble.innerHTML = "";
        bubble.appendChild(wrapper);
    }

    document.addEventListener("DOMContentLoaded", init);
})();
