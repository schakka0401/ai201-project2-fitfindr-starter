"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# Groq model used for the LLM-backed tools. llama-3.3-70b is fast and capable
# enough for short styling/caption generation.
_MODEL = "llama-3.3-70b-versatile"

# Words that carry no matching signal — stripped before keyword scoring so that
# filler like "a vintage tee under" only scores on "vintage" and "tee".
_STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "with", "in", "on", "of", "to",
    "i", "im", "i'm", "am", "looking", "want", "need", "find", "some",
    "under", "below", "less", "than", "max", "size", "sized", "price",
    "cheap", "around", "about", "my", "me", "something", "anything",
    "that", "this", "is", "are", "be", "can", "you", "please", "would",
}


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _llm(messages: list[dict], temperature: float = 0.7, max_tokens: int = 400) -> str:
    """Run a chat completion against Groq and return the response text."""
    client = _get_groq_client()
    resp = client.chat.completions.create(
        model=_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumerics, and drop stopwords."""
    words = re.findall(r"[a-z0-9']+", text.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()
    keywords = _tokenize(description)

    scored = []
    for item in listings:
        # 1. Price filter (inclusive).
        if max_price is not None and item["price"] > max_price:
            continue

        # 2. Size filter — flexible, case-insensitive. The requested size matches
        #    if it appears as a token within the listing's size string, so "M"
        #    matches "M" and "S/M", and "8" matches "8" or "W8 L30".
        if size:
            size_tokens = re.findall(r"[a-z0-9]+", item["size"].lower())
            if size.strip().lower() not in size_tokens:
                continue

        # 3. Score by keyword overlap against title, description, and style_tags.
        haystack = " ".join([
            item["title"],
            item["description"],
            " ".join(item["style_tags"]),
            item["category"],
        ]).lower()
        score = sum(1 for kw in keywords if kw in haystack)

        # 4. Drop listings with no relevant match. If the user gave no usable
        #    keywords at all, keep everything that passed the size/price filters.
        if keywords and score == 0:
            continue

        scored.append((score, item))

    # 5. Sort by score, highest first (stable — preserves dataset order on ties).
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item_desc = (
        f"{new_item['title']} (category: {new_item['category']}, "
        f"style: {', '.join(new_item['style_tags'])}, "
        f"colors: {', '.join(new_item['colors'])})"
    )

    items = wardrobe.get("items", []) if wardrobe else []

    if not items:
        # Empty wardrobe — give general styling advice for the piece on its own.
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a sharp, friendly personal stylist. Keep advice "
                    "concrete and concise — 2 to 4 sentences, no bullet points."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"I'm thinking about buying this secondhand piece: {item_desc}. "
                    "I haven't told you what's in my closet. Suggest what kinds of "
                    "pieces (categories, colors, vibe) would pair well with it and "
                    "what occasions it suits."
                ),
            },
        ]
        return _llm(messages, temperature=0.7)

    # Non-empty wardrobe — suggest specific combinations using named pieces.
    wardrobe_lines = "\n".join(
        f"- {it['name']} ({it['category']}; "
        f"{', '.join(it.get('style_tags', []))})"
        for it in items
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a sharp, friendly personal stylist. You build outfits "
                "ONLY from the new item plus pieces the user actually owns — never "
                "invent items they don't have. Suggest 1 or 2 complete outfits, "
                "naming the specific wardrobe pieces you'd pair with the new item "
                "and briefly why it works. Keep it to a short paragraph or two."
            ),
        },
        {
            "role": "user",
            "content": (
                f"New piece I'm considering: {item_desc}.\n\n"
                f"Here's what's in my closet:\n{wardrobe_lines}\n\n"
                "How would you style the new piece with what I own?"
            ),
        },
    ]
    return _llm(messages, temperature=0.7)


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against an empty or whitespace-only outfit string.
    if not outfit or not outfit.strip():
        return (
            "I don't have enough outfit details to generate a fit card — "
            "let me re-run the outfit suggestion first."
        )

    # 2. Build a prompt with the item details and the styled outfit.
    item_line = (
        f"{new_item['title']} — ${new_item['price']:.2f} on {new_item['platform']}"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You write short, authentic Instagram/TikTok outfit captions — the "
                "way a real person posts an OOTD, not a product listing. 2 to 4 "
                "sentences. Mention the item name, its price, and the platform "
                "naturally, once each. Capture the specific vibe of the outfit. End "
                "with 4 to 6 relevant style hashtags on their own line. Be casual "
                "and a little playful; no corporate copy."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Thrifted find: {item_line}.\n\n"
                f"How it's being styled:\n{outfit}\n\n"
                "Write the caption."
            ),
        },
    ]
    # 3. Higher temperature so different outfits read differently.
    return _llm(messages, temperature=0.9)
