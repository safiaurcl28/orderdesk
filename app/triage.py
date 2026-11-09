"""Sort a customer's message about an online order by urgency and category.

Uses the Claude API when ANTHROPIC_API_KEY is set. The model's answer is validated:
if it is not valid JSON with allowed values, we fall back to simple rules instead of
trusting it. Without an API key the rules are used directly, so tests and CI never
depend on a network call.
"""
import json
import os

URGENCIES = {"low", "medium", "high"}
CATEGORIES = {"allergy_safety", "not_delivered", "missing_or_wrong_item", "quality", "payment", "other"}

PROMPT = """You triage customer messages about online food orders from a restaurant.
Reply with JSON only, in exactly this shape:
{{"urgency": "low" | "medium" | "high", "category": "allergy_safety" | "not_delivered" | "missing_or_wrong_item" | "quality" | "payment" | "other"}}

high = a health or safety risk (allergen, wrong dietary order, food poisoning) or the order never arrived
medium = something is missing or wrong, the food quality was bad, or money is involved (double charge, refund)
low = questions and everything else (opening hours, menu, feedback)

Message: {message}"""

RULES = [
    # (keywords, category, urgency): checked in order, first match wins
    (("allergy", "allergic", "allergen", "nuts", "gluten", "vegan", "sick", "food poisoning"), "allergy_safety", "high"),
    (("never arrived", "not arrived", "hasn't arrived", "still waiting", "where is my order", "late"), "not_delivered", "high"),
    (("missing", "forgot", "wrong order", "wrong item", "not what i ordered"), "missing_or_wrong_item", "medium"),
    (("cold", "soggy", "spilled", "burnt", "raw"), "quality", "medium"),
    (("charged twice", "double", "refund", "payment", "invoice", "overcharged"), "payment", "medium"),
]


def rule_based(message: str) -> dict:
    text = message.lower()
    for keywords, category, urgency in RULES:
        if any(word in text for word in keywords):
            return {"urgency": urgency, "category": category, "source": "rules"}
    return {"urgency": "low", "category": "other", "source": "rules"}


def validate(raw: str) -> dict | None:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if parsed.get("urgency") in URGENCIES and parsed.get("category") in CATEGORIES:
        return {"urgency": parsed["urgency"], "category": parsed["category"], "source": "llm"}
    return None


def triage(message: str) -> dict:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return rule_based(message)
    try:
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=os.getenv("TRIAGE_MODEL", "claude-haiku-5-5"),
            max_tokens=100,
            messages=[{"role": "user", "content": PROMPT.format(message=message)}],
        )
        result = validate(response.content[0].text)
    except Exception:
        result = None
    return result or rule_based(message)
