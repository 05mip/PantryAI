# PantryAI — Project Summary

## Table of Contents

- [Overview](#overview)
- [Problem Statement](#problem-statement)
- [Solution](#solution)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [AWS Services](#aws-services)
- [Database Design](#database-design)
- [Backend API](#backend-api)
- [Frontend](#frontend)
- [Core Features](#core-features)
- [Chef Charlie — AI Chat Assistant](#chef-charlie--ai-chat-assistant)
- [Recipe Matching Engine](#recipe-matching-engine)
- [Infrastructure & Setup](#infrastructure--setup)
- [Challenges & Solutions](#challenges--solutions)
- [Future Enhancements](#future-enhancements)

---

## Overview

PantryAI is a smart pantry and meal planning web application that helps users manage what's in their kitchen, discover recipes based on available ingredients, plan weekly meals, maintain grocery lists, and interact with an AI-powered kitchen assistant named Chef Charlie. The app is built with a Python/Flask backend, vanilla HTML/CSS/JavaScript frontend, and leverages multiple AWS services including DynamoDB, Bedrock (Claude), OpenSearch Serverless, S3, SQS, CloudWatch, and EventBridge.

---

## Problem Statement

Home cooks face several recurring pain points:

1. **Food waste** — People forget what's in their pantry, buy duplicates, and let ingredients expire before using them.
2. **Decision fatigue** — "What can I even make with what I have?" is a daily struggle. Manually cross-referencing ingredients against hundreds of recipes is impractical.
3. **Disconnected workflows** — Pantry tracking, recipe browsing, grocery shopping, and meal planning are typically done in separate apps or on paper, with no integration between them.
4. **Grocery inefficiency** — Without knowing what's already on hand, people overbuy or make multiple store trips for forgotten items.
5. **Lack of personalization** — Generic meal plans don't account for what you already own, your dietary goals, or your preferences.

---

## Solution

PantryAI unifies the entire kitchen workflow into a single application:

- **Smart Pantry Tracking** — Maintain an inventory of everything you have, organized by category with expiry tracking.
- **Intelligent Recipe Matching** — Automatically score every recipe by how many ingredients you already own, surfacing what you can make right now and what you're one or two items away from.
- **Integrated Grocery Lists** — Add missing ingredients from recipes directly to your grocery list. Move purchased items back to the pantry with one click.
- **Weekly Meal Planner** — Plan a 7-day, 3-meal grid. See a grocery preview that shows exactly what you need to buy, already have, or are short on.
- **AI Kitchen Assistant (Chef Charlie)** — A conversational AI that sees your pantry, recipes, grocery list, and meal plan in real time. It can propose personalized meal plans, generate new recipes from scratch, suggest grocery items, recommend ingredient substitutions, and take confirmed actions on your behalf.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12, Flask, Flask-CORS, Gunicorn |
| **Frontend** | Vanilla HTML5, CSS3, JavaScript (ES6+), Jinja2 templates |
| **Database** | AWS DynamoDB (5 tables, pay-per-request) |
| **Search** | AWS OpenSearch Serverless (AOSS) |
| **AI/LLM** | AWS Bedrock — Claude Sonnet 4.6 (`us.anthropic.claude-sonnet-4-6`) |
| **Monitoring** | AWS CloudWatch (logs, metric alarms) |

### Python Dependencies

```
flask, flask-cors, boto3, requests, opensearch-py, python-dotenv, gunicorn, requests-aws4auth
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser (Client)                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ pantry.js │ │recipes.js│ │grocery.js│ │   chat.js     │  │
│  │ meals.js  │ │          │ │          │ │ (Chef Charlie)│  │
│  └─────┬─────┘ └─────┬────┘ └─────┬────┘ └──────┬────────┘  │
│        │             │            │              │           │
│        └─────────────┴────────────┴──────────────┘           │
│                         fetch() / apiFetch()                 │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP JSON
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    Flask Application (app.py)                 │
│  ┌────────────┐ ┌────────────┐ ┌──────────┐ ┌────────────┐  │
│  │ pantry_bp  │ │ recipes_bp │ │grocery_bp│ │  meals_bp   │  │
│  │ /api/pantry│ │/api/recipes│ │/api/groc.│ │ /api/meals  │  │
│  └─────┬──────┘ └─────┬──────┘ └────┬─────┘ └─────┬──────┘  │
│        │              │             │              │          │
│  ┌─────┴──────────────┴─────────────┴──────────────┴──────┐  │
│  │                   Service Layer                         │  │
│  │  dynamo.py │ matching.py │ bedrock.py │ chat.py        │  │
│  │  opensearch.py │ s3.py │ sqs.py                        │  │
│  └──────┬────────┬──────────┬─────────────┬───────────────┘  │
└─────────┼────────┼──────────┼─────────────┼──────────────────┘
          │        │          │             │
          ▼        ▼          ▼             ▼
     DynamoDB   OpenSearch   Bedrock       S3 / SQS
     (5 tables) Serverless   (Claude)
```

---

## AWS Services

### DynamoDB

The primary datastore. Five tables with pay-per-request billing:

| Table | Purpose | Key Schema |
|-------|---------|------------|
| `pai-pantry` | User's kitchen inventory | PK: `user_id`, SK: `item_id` |
| `pai-recipes` | Recipe database | PK: `recipe_id` |
| `pai-favorites` | User-recipe favorites | PK: `user_id`, SK: `recipe_id` |
| `pai-grocery-lists` | Shopping lists | PK: `user_id`, SK: `item_id` |
| `pai-meal-plans` | Weekly meal slots | PK: `user_id`, SK: `slot_id` |

**Global Secondary Indexes:**
- `pai-pantry` → `name-index` (user_id + name) for duplicate detection on add
- `pai-recipes` → `cuisine-index` (cuisine) for filtering

**DynamoDB Streams:** Enabled on `pai-recipes` (NEW_AND_OLD_IMAGES) to sync changes to OpenSearch via Lambda.

### Bedrock (Claude)

Powers four AI features:
1. **Chef Charlie** — Multi-turn conversational assistant via `call_bedrock_conversation()` with a system prompt containing live app data context
2. **Recipe Generation** — `POST /api/recipes/generate` creates full recipes (ingredients, instructions) from just titles
3. **Smart Grocery Suggestions** — Analyzes near-miss recipes and recommends the fewest items to buy that unlock the most recipes
4. **Recipe Import from URL** — `POST /api/recipes/import-url` fetches a webpage, sends the HTML to Claude to extract structured recipe data (title, ingredients, instructions, image URL), and returns it for the user to review and save

Model: `us.anthropic.claude-sonnet-4-6` via cross-region inference profile.

### OpenSearch Serverless (AOSS)

- Collection: `pai-recipes`
- Index: `recipes` with fields for title, cuisine, ingredients, tags
- Authenticated via SigV4 (`requests-aws4auth` with `aoss` service)
- Used for full-text recipe search with relevance ranking
- Falls back to DynamoDB scan with substring matching if OpenSearch is unavailable

### S3

Two buckets:
- `pai-recipe-images` — Recipe photos cached from source URLs. When a user expands a recipe card, the frontend requests the image via `GET /api/recipes/<id>/image`. The backend checks S3 first; if not cached, it downloads from the original source URL (e.g., TheMealDB), uploads to S3, and returns the cached S3 URL for future requests.
- `pai-static-assets` — App static files

### SQS

- Queue: `pai-scrape-queue`
- Used for async recipe scraping jobs (Lambda consumer parses JSON-LD recipe data from URLs)

### CloudWatch

- Log groups: `/pantryai/flask`, `/pantryai/lambda`
- Metric alarms: DynamoDB throttle events, Bedrock throttle events
- Retention: 30 days

### EventBridge

- Optional weekly schedule rule to trigger the scraper Lambda

---

## Database Design

### Pantry Item

```json
{
  "user_id": "default-user",
  "item_id": "uuid",
  "name": "chicken breast",
  "quantity": 2,
  "unit": "lb",
  "category": "Protein",
  "expiry_date": "2026-04-25",
  "added_at": "2026-04-18T10:00:00Z"
}
```

### Recipe

```json
{
  "recipe_id": "uuid",
  "title": "Marry Me Chicken",
  "cuisine": "Italian",
  "prep_time_mins": 35,
  "servings": 4,
  "ingredients": [
    { "name": "chicken breast", "quantity": 2, "unit": "lb" },
    { "name": "sun-dried tomatoes", "quantity": 0.5, "unit": "cup" }
  ],
  "instructions": "Step 1: Season chicken...\nStep 2: Sear...",
  "tags": ["dinner", "comfort food"],
  "created_at": "2026-04-18T10:00:00Z"
}
```

### Grocery Item

```json
{
  "user_id": "default-user",
  "item_id": "uuid",
  "name": "broccoli",
  "quantity": 2,
  "unit": "heads",
  "checked": false,
  "source": "chef_charlie",
  "recipe_id": "optional-recipe-ref",
  "added_at": "2026-04-18T10:00:00Z"
}
```

### Meal Slot

```json
{
  "user_id": "default-user",
  "slot_id": "2026-16-Mon-breakfast",
  "recipe_id": "uuid",
  "recipe_title": "Protein Oat Bowl",
  "servings": 1
}
```

Slot ID format: `{YYYY}-{WW}-{Day}-{meal}` where Day ∈ {Mon..Sun}, meal ∈ {breakfast, lunch, dinner}.

---

## Backend API

### Pantry (`/api/pantry`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/pantry` | List all pantry items for current user |
| POST | `/api/pantry` | Add item (auto-merges if same normalized name exists) |
| PUT | `/api/pantry/<item_id>` | Update quantity, unit, expiry, category, or name |
| DELETE | `/api/pantry/<item_id>` | Remove item |
| POST | `/api/pantry/bulk` | Bulk add multiple items |
| GET | `/api/pantry/categories` | List distinct categories |

### Recipes (`/api/recipes`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/recipes` | Paginated recipe list |
| POST | `/api/recipes` | Create a recipe manually (supports `image_url` field) |
| POST | `/api/recipes/generate` | AI-generate full recipes from title list (Bedrock) |
| POST | `/api/recipes/import-url` | Fetch URL, extract recipe via Bedrock, return structured data |
| GET | `/api/recipes/search?q=` | Full-text search (OpenSearch → fallback scan) with pantry scoring |
| GET | `/api/recipes/matches` | Top 50 recipes ranked by pantry match percentage |
| GET | `/api/recipes/near-matches` | Recipes missing 1–N ingredients |
| GET | `/api/recipes/smart-suggestions` | AI-powered "buy X to unlock Y recipes" |
| GET | `/api/recipes/<id>` | Recipe detail |
| GET | `/api/recipes/<id>/image` | Recipe image URL (S3 cached, lazy-loaded) |
| POST | `/api/recipes/<id>/favorite` | Toggle favorite |
| GET | `/api/recipes/favorites` | List user's favorites |

### Grocery (`/api/grocery`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/grocery` | List items (unchecked first, then checked) |
| POST | `/api/grocery` | Add item (skips if already on list) |
| PUT | `/api/grocery/<item_id>` | Update checked status, quantity, etc. |
| DELETE | `/api/grocery/<item_id>` | Delete single item |
| DELETE | `/api/grocery/checked` | Clear all checked items |
| DELETE | `/api/grocery/all` | Clear entire list |
| POST | `/api/grocery/from-recipe/<id>` | Add missing ingredients from a recipe |
| POST | `/api/grocery/from-meal-plan` | Add all needed items for the week's plan |
| POST | `/api/grocery/to-pantry` | Move checked items to pantry |

### Meal Planner (`/api/meals`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/meals?week=YYYY-WW` | Week grid with dates and filled slots |
| PUT | `/api/meals/<slot_id>` | Assign a recipe to a slot |
| DELETE | `/api/meals/<slot_id>` | Clear a slot |
| GET | `/api/meals/grocery-preview?week=` | Need/partial/have breakdown for the week |

### Chat (`/api/chat`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Send message to Chef Charlie, receive structured blocks |

---

## Frontend

### Design

- **Font:** Inter (Google Fonts)
- **Color scheme:** Green primary (`#2d6a4f`), white background, light grey surfaces
- **Component library:** Custom — cards, pills, badges, toasts, skeleton loaders, modals
- **Responsive:** Mobile-optimized with CSS Grid and Flexbox

### Pages

#### Pantry (`/pantry`)
- Search/filter bar
- Collapsible add form (name, quantity, unit, category, expiry date)
- Items grouped by category with collapsible sections
- Inline quantity/unit editing
- Expiry badges (green/yellow/red based on days remaining)
- Delete with optimistic UI update

#### Recipes (`/recipes`)
- Debounced search powered by OpenSearch
- **Recipe import from URL** — paste any recipe page URL, Bedrock extracts the title, ingredients, instructions, cuisine, and image; auto-fills the form for review before saving
- Manual recipe creation form (title, cuisine, prep time, servings, ingredients, instructions)
- Two tabs: "What I Can Make" (full matches) and "Near Matches" (1–N missing)
- Cuisine dropdown filter, max-missing slider, favorites-first sorting
- Recipe cards with match percentage bar (green/yellow/red), cuisine pill, missing ingredient pills
- **Expandable detail view with recipe images** — images are lazy-loaded when a card is expanded, fetched through an S3 caching proxy
- Heart button to toggle favorites
- "Add missing to grocery list" button per recipe

#### Grocery List (`/grocery`)
- Inline add form
- Checkbox to mark items as purchased
- Per-item delete
- "Clear Checked" and "Clear All" buttons
- "Move Checked to Pantry" — transfers purchased items to pantry inventory
- Collapsible "Smart Suggestions" panel (AI-powered: "buy X to unlock Y recipes")

#### Meal Planner (`/meals`)
- Week navigation (prev/next) with current week as default
- 7×3 grid (Mon–Sun × Breakfast/Lunch/Dinner)
- Current day column highlighted (green tint)
- Click cell → recipe search dropdown (position: fixed, no clipping)
- Adjustable servings per slot
- Clear individual slots (no page flash — local state update)
- "Generate grocery list for this week" — shows need/partial/have sections
- "Add all to grocery list" button

### Chef Charlie Widget (all pages)
- Floating chef hat button (bottom-right, z-index 210)
- Unread indicator (green dot when minimized)
- Slide-up panel (400×520px) with header, message area, input
- Welcome state with 6 clickable example prompts
- User/assistant message bubbles
- Typing indicator (animated dots)
- New conversation button (pencil icon in header)
- Rich content block rendering (see below)

---

## Core Features

### 1. Pantry Management
Track everything in your kitchen with quantities, units, categories, and expiry dates. The system normalizes ingredient names (strips adjectives like "fresh" or "chopped", handles plurals) so "2 fresh chicken breasts" and "chicken breast" are recognized as the same item.

### 2. Intelligent Recipe Matching
Every recipe is scored against your current pantry in real time. The matching engine normalizes both pantry item names and recipe ingredient names, then calculates a percentage match. This powers three views:
- **Full matches** — Recipes you can make right now (sorted by match %)
- **Near matches** — Recipes you're 1–4 ingredients away from
- **Smart suggestions** — AI analyzes near-miss recipes and recommends the fewest purchases to unlock the most meals

### 3. Integrated Grocery List
The grocery list connects to every other feature:
- Add items manually
- Add missing ingredients from any recipe with one click
- Generate a grocery list from the entire week's meal plan
- AI (Chef Charlie) can propose and add items
- Move purchased items to pantry inventory

### 4. Weekly Meal Planner
A visual 7×3 grid for planning breakfast, lunch, and dinner across the week. Each cell supports recipe search, adjustable servings, and links to the grocery preview which shows exactly what you need to buy. The current day is highlighted for quick reference.

### 5. Recipe Search
Full-text search via OpenSearch Serverless with SigV4 authentication. Results include pantry match scores, so you can see which search results you can actually make. Falls back to DynamoDB substring matching if OpenSearch is unavailable.

### 6. Recipe Images
Recipe images are displayed when expanding a recipe card. The system uses a lazy-loading pattern with S3 caching:
1. User clicks to expand a recipe card
2. Frontend calls `GET /api/recipes/<id>/image`
3. Backend checks if a cached version exists in S3 (`pai-recipe-images` bucket)
4. If not cached, downloads from the source URL stored in the recipe record, uploads to S3, returns the S3 URL
5. Subsequent requests return the cached S3 URL directly

Images from imported recipes (via URL import) are automatically captured and stored.

### 7. Recipe Import from URL
Users can import recipes from any website by pasting a URL into the add recipe form:
1. User pastes a URL (e.g., from AllRecipes, Food Network, any blog)
2. Backend fetches the page HTML (first 30KB for token efficiency)
3. Bedrock (Claude) extracts the structured recipe: title, cuisine, prep time, servings, ingredients (with quantities and units), instructions, and the main recipe image URL
4. The form auto-fills with all extracted data for the user to review, edit, and save
5. If an image URL was found, it's saved with the recipe for later display

---

## Chef Charlie — AI Chat Assistant

Chef Charlie is a conversational AI assistant woven into every page of the app. It's powered by AWS Bedrock (Claude Sonnet 4.6) and has real-time access to all app data.

### How It Works

1. **User sends a message** via the floating chat widget
2. **Backend gathers context** — current pantry items, grocery list, this week's meal plan, favorited recipes, and the top 50 recipes by pantry match score
3. **System prompt is built** with all context data embedded, plus rules for response format
4. **Bedrock processes** the conversation (up to 10 turns of history)
5. **Response is parsed** into structured blocks (JSON) or falls back to plain text
6. **Frontend renders** rich interactive blocks with action buttons

### Rich Content Blocks

| Block Type | Renders As | Action Buttons |
|------------|-----------|----------------|
| `text` | Chat bubble with bold/line break support | — |
| `meal_plan_proposal` | Compact 7×3 mini-grid | "Fill out this week's meal plan" / "No thanks" |
| `grocery_proposal` | Checklist with checkboxes | "Add to grocery list" / "Skip" |
| `recipe_proposal` | Recipe card (title, cuisine, ingredients, instructions) | "Save this recipe" / "Dismiss" |
| `substitution` | Swap card (original → substitute, ratio, notes) | — |

### Action Execution

Charlie never auto-executes actions. When a user clicks an action button:
- **Fill meal plan** → Searches for existing recipes by title, batch-generates missing ones via Bedrock (`POST /api/recipes/generate`), then fills each slot via `PUT /api/meals/{slot_id}`
- **Add to grocery** → Calls `POST /api/grocery` for each selected item
- **Save recipe** → Calls `POST /api/recipes` with the full recipe data

### Example Interactions

- *"I'm bulking this week"* → Reviews pantry, proposes a high-protein 7-day meal plan with macro estimates, suggests grocery additions, offers to fill the planner
- *"Make a recipe for marry me chicken"* → Generates a full recipe with ingredients, instructions, cuisine tag, and prep time; offers to save it
- *"I'm out of heavy cream — what can I substitute?"* → Returns a substitution card with coconut cream, the ratio, and flavor notes
- *"What can I make with what's in my pantry?"* → Checks pantry items, suggests 3–5 recipes with match scores, explains what each uses

---

## Recipe Matching Engine

The matching engine in `services/matching.py` is a programmatic (non-LLM) ingredient comparison system.

### Normalization Pipeline

1. Lowercase and strip whitespace
2. Remove leading quantities and units via regex (e.g., "2 cups" → remainder)
3. Strip common adjectives: fresh, frozen, chopped, diced, minced, boneless, skinless, large, small, medium, etc.
4. Trim trailing punctuation

**Example:** `"2 cups fresh diced chicken breast"` → `"chicken breast"`

### Matching Logic

For each recipe ingredient against the pantry:
1. **Exact match** on normalized names
2. **Depluralize** — if the last word is >4 chars and ends in 's', try without the 's'
3. **Substring containment** — check both directions (pantry item name contains ingredient name, or vice versa), including depluralized forms

This handles cases like "chicken" matching "chicken breast", or "tomatoes" matching "tomato".

### Scoring

```
score = round(matched_count / total_ingredient_count * 100)
```

The score is presence-only (does not compare quantities). Quantity comparison happens separately in the grocery preview feature.

---

## Infrastructure & Setup

### Local Development

```bash
cd pantryai
pip install -r requirements.txt
cp .env.example .env        # Fill in AWS credentials
python create_tables.py     # One-time DynamoDB setup
python seed_recipes.py      # Populate recipe database from TheMealDB
python app.py               # Start Flask dev server on :5000
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `AWS_REGION` | AWS region (default: `us-west-2`) |
| `AWS_ACCESS_KEY_ID` | IAM credentials for local dev |
| `AWS_SECRET_ACCESS_KEY` | IAM credentials for local dev |
| `OPENSEARCH_ENDPOINT` | OpenSearch Serverless collection endpoint |
| `SQS_SCRAPE_QUEUE_URL` | SQS queue URL for scrape jobs |
| `FLASK_SECRET_KEY` | Flask session secret |

### Production Deployment

Includes a `Procfile` for AWS Elastic Beanstalk:
```
web: gunicorn app:app --workers 4 --bind 0.0.0.0:8000 --timeout 60
```

### Lambda Functions

| Function | Trigger | Purpose |
|----------|---------|---------|
| `lambda_opensearch_sync` | DynamoDB Streams (pai-recipes) | Sync recipe CRUD to OpenSearch index |
| `lambda_scraper` | SQS (pai-scrape-queue) | Scrape recipes from URLs via JSON-LD parsing |

---

## Challenges & Solutions

### 1. AWS IAM Permission Layering

**Challenge:** DynamoDB, OpenSearch Serverless, and Bedrock each have different IAM permission models. The initial IAM user had no permissions, and errors surfaced incrementally — first `AccessDeniedException` on DynamoDB, then on OpenSearch, then on Bedrock.

**Solution:** Iteratively added IAM policies:
- `AmazonDynamoDBFullAccess` for DynamoDB operations
- Custom inline policy for `aoss:*` (OpenSearch Serverless uses different IAM actions than classic OpenSearch's `es:*` — the managed `AmazonOpenSearchServiceFullAccess` policy doesn't cover Serverless)
- Bedrock model access via the AWS console's model access management

### 2. OpenSearch Serverless Authentication

**Challenge:** OpenSearch Serverless (AOSS) requires SigV4 signing with the `aoss` service name, not `es`. Initial attempts used default boto3 credential chains that didn't properly load environment variables in standalone scripts, resulting in 403 errors.

**Solution:** Explicitly constructed `AWS4Auth` credentials from environment variables (`os.environ`) rather than relying on `boto3.Session().get_credentials()`. This ensured consistent authentication across both the Flask app and standalone scripts.

### 3. Bedrock Model ID for Cross-Region Inference

**Challenge:** The Claude Sonnet 4.6 model (`anthropic.claude-sonnet-4-6`) requires a cross-region inference profile. Using the raw model ID directly returned `ValidationException: Invocation of model ID with on-demand throughput isn't supported`.

**Solution:** Tested multiple ID formats programmatically and discovered the correct format is `us.anthropic.claude-sonnet-4-6` (prefixed with region group `us.`). Built a diagnostic script that tried multiple candidates to find the working one.

### 4. Meal Plan Slot ID Format Mismatch

**Challenge:** Chef Charlie's meal plan fill feature was failing on all slots. The chat widget JS generated slot IDs with underscores (`2026-16_Mon_breakfast`) while the backend parsed them by splitting on dashes, expecting `2026-16-Mon-breakfast`.

**Solution:** Aligned the chat JS to use dashes in slot IDs, matching the format used by the meal planner page's own JS.

### 5. Recipe Generation for AI-Proposed Meals

**Challenge:** When Chef Charlie proposed creative meal plans (e.g., "Protein Oat Bowl"), those recipes didn't exist in the database. The initial implementation used a placeholder ingredient which failed validation, and even with a fallback, the created "recipes" had no real ingredients or instructions.

**Solution:** Built a batch recipe generation endpoint (`POST /api/recipes/generate`) that:
1. Deduplicates titles (one recipe shared across multiple meal slots)
2. Makes a single Bedrock call to generate full recipes for all titles at once
3. Saves each with real ingredients, instructions, cuisine, and prep time
4. Returns recipe IDs for the meal plan fill to reference

### 6. Environment Variable Loading in Standalone Scripts

**Challenge:** Scripts like `create_tables.py` and `seed_recipes.py` failed with `UnrecognizedClientException` because `boto3` wasn't picking up AWS credentials from the `.env` file — `python-dotenv` wasn't being loaded outside the Flask app.

**Solution:** Added `from dotenv import load_dotenv; load_dotenv()` at the top of every standalone script.

### 7. Meal Planner UI Flash on Slot Removal

**Challenge:** Clearing a meal slot caused the entire weekly grid to disappear and re-render because `clearSlot()` called `loadMeals()`, which cleared the DOM and made a full API round-trip.

**Solution:** Updated `clearSlot()` to modify the local `mealData` object in memory (set the slot to `null`) and call `renderGrid()` directly, avoiding the network request and DOM teardown.

### 8. Meal Search Dropdown Clipping

**Challenge:** The recipe search dropdown inside meal cells was getting clipped by the grid's `overflow-x: auto`, forcing users to scroll the entire calendar to see search results.

**Solution:** Switched the dropdown to `position: fixed` and calculated its coordinates via JavaScript relative to the input field's `getBoundingClientRect()`. Added a scroll listener to reposition on scroll. Moved `overflow-x: auto` to a wrapper div so the grid itself has `overflow: visible`.

---

## Future Enhancements

- **User Authentication** — Introduce AWS Cognito (or similar) for multi-user support
- **Persistent Chat History** — Store Chef Charlie conversations in a `pai-conversations` DynamoDB table
- **Nutritional Data** — Add calorie/macro tracking per recipe and meal plan
- **Shopping List Sharing** — Export grocery lists or share with family members
- **OpenSearch Full Integration** — Complete the DynamoDB Streams → OpenSearch sync pipeline for real-time search indexing
- **Mobile PWA** — Add service worker and manifest for installable mobile experience
- **Expiry Notifications** — Alert users when pantry items are about to expire
- **Barcode Scanning** — Scan grocery items to add to pantry
- **Recipe Photo Upload** — Allow users to upload their own recipe photos
