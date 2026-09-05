"""
Gemini client — buyer-client side.
Used only for:
  1. Intent parsing:  intent string → structured filter
  2. "Why" bullet text generation for the DecisionReceipt

This lives in buyer-client/, NOT in backend/.
The Gateway (backend) is deterministic — no LLM calls there.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import google.generativeai as genai


def _get_model() -> genai.GenerativeModel:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-1.5-flash")


def parse_intent(intent: str) -> dict[str, Any]:
    """
    Turn a free-text buyer intent string into a structured search filter.
    Returns: { "category": str|None, "max_price": float|None, "keywords": list[str] }

    Falls back to deterministic keyword heuristics if Gemini is unavailable
    (no API key set or API error).
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return _parse_intent_heuristic(intent)

    try:
        model = _get_model()
        prompt = f"""You are a structured data extractor for a commerce search system.

Extract from this buyer request: "{intent}"

Return ONLY a valid JSON object with these exact keys:
- "category": one of ["footwear", "accessories"] or null if unclear
- "max_price": a number (INR) if a price limit is mentioned, otherwise null
- "keywords": a list of relevant search keywords (e.g. ["running", "shoes"])

Examples:
  "Find me running shoes under 6000" → {{"category":"footwear","max_price":6000,"keywords":["running","shoes"]}}
  "Buy the premium version" → {{"category":null,"max_price":null,"keywords":["premium"]}}
  "Buy the 8999 version instead" → {{"category":"footwear","max_price":null,"keywords":["premium","8999"]}}

Return ONLY the JSON object, no explanation."""

        response = model.generate_content(prompt)
        text = response.text.strip()
        # Strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        result = json.loads(text)
        return {
            "category": result.get("category"),
            "max_price": float(result["max_price"]) if result.get("max_price") else None,
            "keywords": result.get("keywords", []),
        }
    except Exception as e:
        print(f"[gemini] parse_intent fallback (Gemini error: {e})")
        return _parse_intent_heuristic(intent)


def generate_why_bullets(
    intent: str,
    selected_product: dict,
    score_breakdown: dict,
) -> list[str]:
    """
    Generate human-readable "why" bullets for the DecisionReceipt.
    Falls back to deterministic bullet generation if Gemini is unavailable.

    score_breakdown keys: keyword_score, tag_score, in_stock, within_budget, preferred_category
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return _generate_why_deterministic(score_breakdown)

    try:
        model = _get_model()
        prompt = f"""Generate 3 concise bullet reasons (no bullet symbols) why "{selected_product['name']}" 
was selected for the request: "{intent}".
Use these facts: {json.dumps(score_breakdown)}.
Return ONLY a JSON array of 3 short strings (under 8 words each).
Example: ["Best fit for intent", "In stock", "Within budget"]"""

        response = model.generate_content(prompt)
        text = response.text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        bullets = json.loads(text)
        if isinstance(bullets, list) and all(isinstance(b, str) for b in bullets):
            return bullets[:4]
    except Exception as e:
        print(f"[gemini] generate_why fallback (error: {e})")

    return _generate_why_deterministic(score_breakdown)


def _parse_intent_heuristic(intent: str) -> dict[str, Any]:
    """
    Deterministic fallback for intent parsing.
    Used when GEMINI_API_KEY is not set or Gemini fails.
    """
    text = intent.lower()

    # Category detection — accessory-specific keywords take priority over general "running"
    category: str | None = None
    accessory_words = ["sock", "socks", "insole", "insoles", "cap", "accessory", "accessories",
                       "bottle", "sleeve", "vest", "bag", "sunglasses", "eyewear"]
    footwear_words = ["shoe", "shoes", "boot", "boots", "sneaker", "sneakers", "runner",
                      "runners", "footwear", "trainer", "trainers"]

    if any(w in text for w in accessory_words):
        category = "accessories"
    elif any(w in text for w in footwear_words):
        category = "footwear"
    elif "running" in text:
        # Ambiguous — "running" alone could be footwear or accessories context;
        # default to footwear as the more common purchase intent
        category = "footwear"

    # Price extraction — look for numeric values preceded/followed by price indicators
    max_price: float | None = None
    price_patterns = [
        r"(?:under|below|less than|max|maximum|upto|up to|₹|rs\.?)\s*[\s₹]*([\d,]+)",
        r"([\d,]+)\s*(?:rupees?|inr|/-)",
        # bare 4-5 digit number likely a price
        r"\b(\d{4,5})\b",
    ]
    for pattern in price_patterns:
        m = re.search(pattern, text)
        if m:
            try:
                max_price = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                pass

    # Keywords
    stop_words = {"me", "find", "buy", "get", "the", "a", "an", "i", "want", "need",
                  "under", "below", "less", "than", "for", "in", "at", "of", "and",
                  "version", "instead"}
    keywords = [w for w in re.findall(r"[a-z]+", text) if w not in stop_words and len(w) > 2]

    return {"category": category, "max_price": max_price, "keywords": keywords}


def _generate_why_deterministic(score_breakdown: dict) -> list[str]:
    """Deterministic fallback for why-bullet generation."""
    bullets = []
    if score_breakdown.get("keyword_score", 0) > 0 or score_breakdown.get("tag_score", 0) > 0:
        bullets.append("Best fit for intent")
    if score_breakdown.get("in_stock"):
        bullets.append("In stock")
    if score_breakdown.get("within_budget"):
        bullets.append("Within budget")
    if score_breakdown.get("preferred_category"):
        bullets.append("Merchant preferred category")
    return bullets or ["Best available match"]
