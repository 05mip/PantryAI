# PantryAI

## Inspiration

We've all stood in front of an open fridge wondering "what can I even make with this?" — only to give up and order takeout. Meanwhile, perfectly good ingredients expire and get thrown away. The average American household wastes over $1,500 worth of food per year, and a big part of that comes down to poor visibility into what you already have and how to use it. We wanted to build something that connects the dots between your pantry, your recipes, your grocery list, and your weekly meal plan — all in one place, powered by AI that actually knows what's in your kitchen.

## What it does

PantryAI is a full-stack smart kitchen management app with five core modules:

- **Pantry Tracker** — Keep a live inventory of everything in your kitchen with quantities, categories, and expiry dates.
- **Intelligent Recipe Matching** — Every recipe in the database is scored against your pantry in real time. See what you can make right now, what you're one ingredient away from, and get AI-powered suggestions for the fewest items to buy that unlock the most meals.
- **Grocery List** — Deeply integrated with every other feature. Add missing ingredients from any recipe in one click, generate a full shopping list from your weekly meal plan, and move purchased items back to your pantry when you're done shopping.
- **Weekly Meal Planner** — A visual 7×3 grid for breakfast, lunch, and dinner. Includes a grocery preview that shows exactly what you need to buy, already have, or are short on.
- **Chef Charlie (AI Assistant)** — A conversational AI chef accessible from every page. Chef Charlie sees your pantry, grocery list, meal plan, and recipe database in real time. Ask it to plan a bulking week, create a recipe for marry me chicken, suggest substitutions, or add items to your grocery list — it proposes structured actions and you confirm with a button click.
- **Recipe Import** — Paste any recipe URL (AllRecipes, Food Network, blogs) and Bedrock extracts the full recipe — title, ingredients, instructions, image — and auto-fills the form for you to review and save.

## How we built it

**Backend:** Python 3.12 with Flask, structured as service-layer architecture. Five route blueprints (pantry, recipes, grocery, meals, chat) call into dedicated service modules for DynamoDB, OpenSearch, and Bedrock

**Frontend:** Vanilla HTML/CSS/JavaScript with Jinja2 templates. No framework — just clean, fast DOM manipulation with `fetch()` calls to the JSON API. Custom component library including skeleton loaders, toast notifications, and the Chef Charlie chat widget with rich interactive content blocks.

**AWS Services:**
- **DynamoDB** (5 tables) — All app data such as recipes, pantry contents and meal plans
- **Bedrock (Claude Sonnet 4.6)** — Powers Chef Charlie's multi-turn conversations, recipe generation from titles, recipe import from URLs, and smart grocery suggestions
- **OpenSearch Serverless** — Full-text recipe search with SigV4 authentication, with a DynamoDB fallback
- **CloudWatch** — Logging and throttle alarms

**Recipe Matching Engine:** A deterministic, programmatic (non-LLM) scoring system that normalizes ingredient names by stripping quantities, units, and adjectives ("2 cups fresh diced chicken breast" → "chicken breast"), then uses exact matching, depluralization, and substring containment to calculate a percentage match score against pantry items.

## Challenges we ran into

**AWS permission layering was a maze.** DynamoDB, OpenSearch Serverless, and Bedrock each have different IAM permission models. OpenSearch Serverless uses `aoss:*` actions, not the `es:*` actions covered by the standard `AmazonOpenSearchServiceFullAccess` policy — we had to discover this through trial and error with incremental 403 errors.

**Getting the LLM to return reliably structured JSON** for Chef Charlie's rich content blocks (meal plan grids, grocery checklists, recipe cards) required careful prompt engineering as it's deeply interwoven into the api architecture. The system prompt enforces a strict block-based response format, and the parser gracefully falls back to plain text when the model doesn't comply.

**Meal plan slot ID format mismatch** between the chat widget and the meal planner caused silent failures — underscores vs. dashes in a compound key that only surfaced when 10 out of 21 meal slots failed to fill. Debugging required tracing through three layers: frontend JS, Flask route, and DynamoDB partition keys.

**Recipe sites actively block scrapers.** AllRecipes returns a 403 status code but still serves the full page HTML — we had to learn to ignore HTTP status codes and check content length instead, plus use realistic browser headers.

## Accomplishments that we're proud of

- **Chef Charlie feels useful** It sees your real pantry data, proposes actionable meal plans with interactive grids, and every suggestion can be executed with a button click — no copy-pasting or manual data entry.
- **The recipe matching engine works without any LLM calls.** It's fast, deterministic, and handles real-world ingredient messiness (plurals, adjectives, partial matches) well enough that the "What I Can Make" tab is genuinely useful.
- **Everything is connected.** Add a recipe to your meal plan → see what's missing in the grocery preview → add it to your list → check it off at the store → move it to your pantry → your match scores update. The entire loop works.
- **Recipe import from any URL.** Paste a link, Bedrock reads the page, and the form fills itself out — including the image.
- **Batch recipe generation.** When Chef Charlie proposes 10 creative recipes that don't exist in the database, the system generates all of them in a single Bedrock call with full ingredients and instructions, then fills the meal plan.

## What we learned

- AWS Serverless services (OpenSearch Serverless, DynamoDB on-demand, Bedrock) are powerful but each has its own auth and access model — budget time for IAM troubleshooting and user management.
- LLMs are excellent at structured data extraction (recipe import from HTML) and creative generation (meal planning) but need guardrails — strict JSON response formats and graceful fallbacks.
- A programmatic matching engine can be surprisingly effective compared to vector search for ingredient-level comparisons, and it's orders of magnitude faster and cheaper than LLM calls.
- Building a chat assistant that takes real actions (not just gives advice) requires careful UX: always propose first, let the user confirm, show progress, and handle partial failures gracefully.
- Vanilla JS is perfectly capable for a rich interactive app — no framework needed. The entire frontend is under 1,500 lines of JS across 6 files.

## What's next for PantryAI

- **Multi-user authentication** with AWS Cognito so households can share pantries and meal plans. Users would be able to log in anywhere from any device
- **Nutritional tracking** — calorie and macro data per recipe and across the weekly meal plan, with dietary goal integration into Chef Charlie's suggestions
- **Persistent chat history** in DynamoDB so Chef Charlie remembers past conversations across sessions
- **OpenSearch real-time sync** via DynamoDB Streams and Lambda for instant search indexing as recipes are added
- **Mobile PWA** with service worker for offline pantry access and push notifications for expiring items
- **Barcode scanning** to add grocery items to the pantry by scanning product barcodes
- **Shared grocery lists** — export or share lists with family members in real time
