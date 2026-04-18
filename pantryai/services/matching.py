import re

STRIP_ADJECTIVES = {
    "fresh", "dried", "whole", "ground", "large", "small", "medium",
    "chopped", "minced", "sliced", "diced", "frozen", "canned", "raw",
    "cooked", "boneless", "skinless", "unsalted", "salted", "organic", "ripe",
}

_QTY_RE = re.compile(
    r"^\s*[\d½¼¾⅓⅔⅛/.\- ]+\s*"
    r"(cups?|tbsp|tsp|oz|lb|lbs|g|kg|ml|l|cloves?|pieces?|cans?|stalks?|heads?|bunche?s?|slices?|pinch(?:es)?|dash(?:es)?|sprigs?|handfuls?|count)?\s*",
    re.IGNORECASE,
)


def normalize_ingredient(name: str) -> str:
    if not name:
        return ""
    text = name.lower().strip()
    text = _QTY_RE.sub("", text).strip()
    words = text.split()
    words = [w for w in words if w not in STRIP_ADJECTIVES]
    cleaned = " ".join(words).strip(" ,.-")
    return cleaned if cleaned else text


def _depluralize(word):
    if len(word) > 4 and word.endswith("s"):
        return word[:-1]
    return None


def ingredient_in_pantry(norm_name: str, pantry_names: set) -> bool:
    if not norm_name:
        return False
    if norm_name in pantry_names:
        return True
    dep = _depluralize(norm_name)
    if dep and dep in pantry_names:
        return True
    for pn in pantry_names:
        if norm_name in pn or pn in norm_name:
            return True
        pn_dep = _depluralize(pn)
        if pn_dep and (norm_name in pn_dep or pn_dep in norm_name):
            return True
        if dep and (dep in pn or pn in dep):
            return True
    return False


def score_recipe(pantry_items: list, recipe_ingredients: list) -> dict:
    pantry_names = {normalize_ingredient(i["name"]) for i in pantry_items if i.get("name")}
    pantry_names.discard("")

    matched, missing = [], []
    for ingredient in recipe_ingredients:
        norm = normalize_ingredient(ingredient.get("name", ""))
        if not norm:
            continue
        if ingredient_in_pantry(norm, pantry_names):
            matched.append(ingredient)
        else:
            missing.append(ingredient)

    total = len(matched) + len(missing)
    score = round(len(matched) / total * 100) if total else 0
    return {"score": score, "matched": matched, "missing": missing}
