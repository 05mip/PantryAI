# Chef Charlie — AI Chat Assistant Build Prompt

## Overview

Add "Chef Charlie," a conversational AI assistant to PantryAI, powered by AWS Bedrock (Claude). Chef Charlie is a persistent chat widget accessible from every page via a floating chef icon in the bottom-right corner. It has full read/write access to all app data (pantry, recipes, grocery list, meal plan) and can take actions on the user's behalf after confirmation.

---

## UI / Frontend

### Floating Button
- Fixed-position circular button, bottom-right corner (24px from edges), z-index 200+.
- Displays a chef hat icon (SVG or emoji: 👨‍🍳). On hover, show tooltip: "Chat with Chef Charlie."
- Unread indicator: small green dot when Charlie has responded and the chat is minimized.
- Clicking toggles the chat panel open/closed.

### Chat Panel
- Opens as a slide-up panel anchored to the bottom-right, approximately 400px wide × 520px tall, with a subtle box shadow.
- Header bar: "Chef Charlie" title with a minimize (×) button.
- Scrollable message area with alternating bubbles:
  - User messages: right-aligned, primary green background, white text.
  - Charlie messages: left-aligned, light grey/surface background, dark text.
  - Charlie messages support **rich content blocks** (see below).
- Input area at bottom: text input + send button. Enter key sends. Disable input while waiting for response.
- Show a typing indicator (animated dots) while waiting for Bedrock response.

### Welcome State / Example Prompts
When the chat is first opened (no messages yet), display a welcome message and clickable example prompt chips:

```
Hi! I'm Chef Charlie 👨‍🍳
Your personal kitchen assistant. I can help with meal planning, recipes, grocery lists, and more. Try one of these:

[ "I'm bulking this week — plan my meals" ]
[ "What can I make with what's in my pantry?" ]
[ "I'm out of heavy cream — what can I substitute?" ]
[ "Make a recipe for marry me chicken" ]
[ "I want to eat healthy this week under 2000 calories/day" ]
[ "Add chicken, rice, and broccoli to my grocery list" ]
```

Clicking a chip populates and sends it as a user message.

### Rich Content Blocks in Charlie's Responses
Charlie's messages are not just plain text. The frontend must parse structured JSON action blocks that Charlie returns and render them as interactive UI:

1. **Proposed Meal Plan** — Render an inline 7×3 grid (same visual style as the meal planner page, but compact). Each cell shows recipe title + servings. Below the grid, two action buttons:
   - "Fill out this week's meal plan" → calls `PUT /api/meals/<slot_id>` for each slot.
   - "No thanks" → dismisses the proposal.

2. **Proposed Grocery Additions** — Render a checklist of items. User can uncheck items they don't want. Below:
   - "Add to grocery list" → calls `POST /api/grocery` for each checked item.
   - "Skip" → dismisses.

3. **Proposed Recipe** — Render a recipe card preview (title, cuisine, ingredients list, instructions). Below:
   - "Save this recipe" → calls `POST /api/recipes` to create the recipe.
   - "Edit first" → populates the recipe form on the recipes page with the data.

4. **Pantry Summary** — Render a compact list of current pantry items grouped by category.

5. **Substitution Suggestion** — Render a card: "Instead of {X}, try {Y}" with an optional note about ratio or flavor difference.

The response format from the backend will include a `blocks` array, where each block has a `type` and `data`. The frontend renders each block in order. Plain text blocks are rendered as regular chat bubbles.

---

## Backend

### New Route: `routes/chat.py`

```
POST /api/chat
```

**Request body:**
```json
{
  "message": "I'm bulking this week, plan my meals",
  "conversation_id": "optional-uuid-for-continuity"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "conversation_id": "uuid",
    "blocks": [
      {
        "type": "text",
        "content": "Great! I looked at your pantry and here's what I'd suggest for a high-protein bulking week..."
      },
      {
        "type": "meal_plan_proposal",
        "data": {
          "Mon": { "breakfast": { "title": "Greek Yogurt Bowl", "recipe_id": null, "servings": 1 }, "lunch": {...}, "dinner": {...} },
          "Tue": {...},
          ...
        }
      },
      {
        "type": "grocery_proposal",
        "data": {
          "items": [
            { "name": "chicken breast", "quantity": 3, "unit": "lb" },
            { "name": "broccoli", "quantity": 2, "unit": "heads" }
          ]
        }
      },
      {
        "type": "text",
        "content": "Want me to fill out this week's meal plan and add those items to your grocery list?"
      }
    ]
  }
}
```

### Chat Service: `services/chat.py`

This service orchestrates the Bedrock call. It:

1. **Gathers context** before every Bedrock call by pulling live data from the app:
   - Current pantry items (from `list_pantry`)
   - Current grocery list (from `list_grocery`)
   - Current week's meal plan (from `list_meal_plan`)
   - User's favorited recipe IDs (from `get_user_favorite_ids`)
   - Available recipes sample — top 50 by match score (from `list_all_recipes_cached` + `score_recipe`)

2. **Builds the system prompt** (see below).

3. **Sends to Bedrock** with conversation history (last 10 messages for context window management).

4. **Parses the response** — Claude returns a JSON structure with `blocks`. The service validates the JSON, strips any markdown fencing, and returns it.

5. **Executes confirmed actions** — When the user clicks an action button (e.g., "Fill out meal plan"), the frontend calls dedicated action endpoints or the existing API routes directly. Charlie does NOT auto-execute actions — the user must confirm via the UI buttons.

### System Prompt for Bedrock

```
You are Chef Charlie, a friendly and knowledgeable kitchen assistant inside the PantryAI app. You help users plan meals, manage their pantry, build grocery lists, and discover recipes.

You have access to the user's current app data, provided below as context. Use this data to give personalized, actionable advice.

CURRENT PANTRY:
{pantry_items_json}

CURRENT GROCERY LIST:
{grocery_list_json}

THIS WEEK'S MEAL PLAN:
{meal_plan_json}

RECIPE DATABASE (top matches for user's pantry):
{top_recipes_json}

FAVORITED RECIPES:
{favorite_ids_json}

RULES:
1. Always consider what the user already has in their pantry before suggesting purchases.
2. When proposing a meal plan, return it as a structured block (see format below).
3. When proposing grocery items, return them as a structured block.
4. When creating a new recipe, return it as a structured recipe block with full ingredients (name, quantity, unit) and step-by-step instructions.
5. For substitution questions, explain the substitute, the ratio, and any flavor/texture differences.
6. Be concise but warm. Use a casual, encouraging tone. You're a friendly chef, not a textbook.
7. If the user asks you to do something (add to grocery list, fill meal plan, save a recipe), propose it first and let them confirm — never say you did it directly.
8. When suggesting a meal plan, try to minimize grocery purchases by reusing pantry ingredients across meals.
9. For bulking/cutting/dietary goals, adjust macros accordingly and mention approximate protein/calories when relevant.

RESPONSE FORMAT:
You must return a JSON object with a "blocks" array. Each block is one of:
- {"type": "text", "content": "Your message here"}
- {"type": "meal_plan_proposal", "data": {"Mon": {"breakfast": {"title": "...", "recipe_id": "..." or null, "servings": N}, "lunch": {...}, "dinner": {...}}, "Tue": {...}, ...}}
- {"type": "grocery_proposal", "data": {"items": [{"name": "...", "quantity": N, "unit": "..."}]}}
- {"type": "recipe_proposal", "data": {"title": "...", "cuisine": "...", "prep_time_mins": N, "servings": N, "ingredients": [{"name": "...", "quantity": N, "unit": "..."}], "instructions": "Step 1: ...\nStep 2: ..."}}
- {"type": "substitution", "data": {"original": "...", "substitute": "...", "ratio": "...", "notes": "..."}}

Return ONLY the JSON object. No markdown, no explanation outside the blocks.
```

### Conversation History Storage

Store conversation history in-memory on the Flask side (dict keyed by conversation_id). Each conversation stores the last 10 message pairs. No DynamoDB table needed for this — conversations are ephemeral per session. If you want persistence later, add a `pai-conversations` table.

### Action Execution Flow

When the user clicks an action button in the chat, the frontend calls the existing API routes directly:

- **"Fill out meal plan"** → For each slot in the proposal, `PUT /api/meals/{slot_id}` with `{recipe_id, servings}`. For proposed recipes that don't exist yet (`recipe_id: null`), first `POST /api/recipes` to create them, then use the returned `recipe_id`.
- **"Add to grocery list"** → For each item, `POST /api/grocery` with `{name, quantity, unit, source: "chef_charlie"}`.
- **"Save this recipe"** → `POST /api/recipes` with the full recipe data from the proposal.

The frontend handles this orchestration — no special backend endpoint needed beyond the existing API.

---

## File Changes Summary

### New files:
- `routes/chat.py` — `POST /api/chat` endpoint
- `services/chat.py` — Context gathering, system prompt building, Bedrock orchestration, response parsing
- `static/js/chat.js` — Chat widget: toggle, message rendering, rich block rendering, action button handlers
- `templates/partials/chat.html` — Chat widget HTML (included in `base.html`)

### Modified files:
- `app.py` — Register `chat_bp` blueprint
- `templates/base.html` — Include chat widget partial + `chat.js` script
- `static/css/style.css` — Add styles for chat widget, message bubbles, rich blocks, floating button, typing indicator

### No new dependencies needed — uses existing Bedrock service (`services/bedrock.py`'s `call_bedrock` function).

---

## Edge Cases to Handle

1. **Bedrock timeout/error** — Show a friendly error message in the chat: "Sorry, I'm having trouble thinking right now. Try again in a moment." Don't crash the widget.
2. **Empty pantry** — Charlie should acknowledge it: "Your pantry is empty! Let's start by adding some staples. What do you usually keep on hand?"
3. **Recipe creation with existing title** — If the user asks to create a recipe that already exists in the DB, Charlie should mention it: "I found an existing recipe for that — want to see it, or should I create a new version?"
4. **Very long conversations** — Trim to last 10 messages before sending to Bedrock to stay within context limits.
5. **Proposed recipe with unknown ingredients** — When Charlie proposes a recipe, it may include ingredients not in the standard unit list. Normalize them in the `POST /api/recipes` call.
6. **Multi-step flows** — Charlie should handle follow-ups naturally. If user says "yes, fill it out" after a meal plan proposal, Charlie should understand from context what "it" refers to. Include the last proposal in conversation history.
