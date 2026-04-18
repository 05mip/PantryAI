import json
import logging

import boto3

from config import BEDROCK

logger = logging.getLogger("pantryai")

bedrock_runtime = boto3.client(
    "bedrock-runtime",
    region_name=BEDROCK["region"],
)


def call_bedrock(prompt, max_tokens=4096):
    try:
        response = bedrock_runtime.invoke_model(
            modelId=BEDROCK["model_id"],
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
            }),
        )
        body = json.loads(response["body"].read())
        return body["content"][0]["text"]
    except Exception as e:
        logger.error(f"Bedrock call failed: {e}")
        raise


def call_bedrock_conversation(system_prompt, messages, max_tokens=8192):
    """Multi-turn conversation with a system prompt."""
    try:
        response = bedrock_runtime.invoke_model(
            modelId=BEDROCK["model_id"],
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": messages,
            }),
        )
        body = json.loads(response["body"].read())
        return body["content"][0]["text"]
    except Exception as e:
        logger.error(f"Bedrock conversation call failed: {e}")
        raise


def get_smart_grocery_suggestions(missing_by_recipe):
    """
    missing_by_recipe: dict mapping recipe_title -> list of missing ingredient names
    Returns list of suggestions or fallback list.
    """
    prompt = f"""You are a helpful chef assistant. The user's pantry is missing these ingredients across multiple recipes:

{json.dumps(missing_by_recipe, indent=2)}

Suggest the optimal grocery list: the fewest items to buy that unlock the most recipes.
For each suggested item, list which recipes it unlocks.

Return ONLY a valid JSON object, no explanation:
{{
  "suggestions": [
    {{
      "item": "ingredient name",
      "unlocks_recipes": ["Recipe Title 1", "Recipe Title 2"]
    }}
  ]
}}"""

    try:
        raw = call_bedrock(prompt)
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        result = json.loads(text)
        return result.get("suggestions", [])
    except Exception as e:
        logger.error(f"Bedrock smart suggestions failed, falling back: {e}")
        return _fallback_suggestions(missing_by_recipe)


def _fallback_suggestions(missing_by_recipe):
    """Frequency-based fallback: count missing ingredients across recipes, return top 10."""
    freq = {}
    for title, ingredients in missing_by_recipe.items():
        for ing in ingredients:
            name = ing if isinstance(ing, str) else ing.get("name", "")
            name = name.lower().strip()
            if name:
                if name not in freq:
                    freq[name] = {"count": 0, "recipes": []}
                freq[name]["count"] += 1
                freq[name]["recipes"].append(title)

    sorted_items = sorted(freq.items(), key=lambda x: x[1]["count"], reverse=True)
    return [
        {"item": name, "unlocks_recipes": data["recipes"]}
        for name, data in sorted_items[:10]
    ]
