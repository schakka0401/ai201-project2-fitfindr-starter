"""
Unit tests for the three FitFindr tools.

search_listings is pure Python and is tested for real. The two LLM-backed tools
(suggest_outfit, create_fit_card) are tested with their network call monkey-
patched out, so the suite is deterministic and runs offline — except the
empty-input guards, which never touch the LLM and are tested for real.

Run from the repo root:  pytest tests/
"""

import tools
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ─────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Nothing in the dataset matches — must be an empty list, not an exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_is_flexible():
    # "M" must match a listing whose size is "S/M" (token-based, case-insensitive).
    results = search_listings("baby tee", size="M", max_price=50)
    assert any(r["id"] == "lst_002" for r in results)  # the S/M Y2K Baby Tee


def test_search_size_filter_excludes_mismatches():
    results = search_listings("vintage tee", size="XXL", max_price=200)
    assert all("xxl" in r["size"].lower() for r in results)


def test_search_returns_full_listing_dicts():
    results = search_listings("vintage", size=None, max_price=200)
    assert results, "expected at least one vintage listing"
    expected = {"id", "title", "description", "category", "style_tags",
                "size", "condition", "price", "colors", "brand", "platform"}
    assert expected <= set(results[0].keys())


def test_search_sorted_by_relevance():
    # More overlapping keywords should rank a listing higher. We can't assert an
    # exact order, but the top result must contain at least as many of the query
    # keywords as the last result.
    kws = ["vintage", "graphic", "tee"]
    results = search_listings("vintage graphic tee", size=None, max_price=200)
    assert len(results) >= 2

    def score(item):
        hay = (item["title"] + " " + item["description"] + " "
               + " ".join(item["style_tags"])).lower()
        return sum(k in hay for k in kws)

    assert score(results[0]) >= score(results[-1])


# ── suggest_outfit ──────────────────────────────────────────────────────────

def test_suggest_outfit_empty_wardrobe_returns_string(monkeypatch):
    monkeypatch.setattr(tools, "_llm", lambda *a, **k: "general styling advice")
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(out, str) and out.strip()


def test_suggest_outfit_uses_owned_pieces(monkeypatch):
    # Capture the prompt sent to the LLM and confirm a real wardrobe piece is in it.
    captured = {}

    def fake_llm(messages, **kwargs):
        captured["prompt"] = " ".join(m["content"] for m in messages)
        return "outfit using your baggy jeans"

    monkeypatch.setattr(tools, "_llm", fake_llm)
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(out, str) and out.strip()
    assert "Baggy straight-leg jeans, dark wash" in captured["prompt"]


# ── create_fit_card ─────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_error_string():
    # Empty outfit must NOT hit the LLM and must NOT raise — returns a message.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("", item)
    assert isinstance(card, str)
    assert "outfit" in card.lower()


def test_create_fit_card_whitespace_outfit_returns_error_string():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("   \n  ", item)
    assert isinstance(card, str) and card.strip()


def test_create_fit_card_builds_caption(monkeypatch):
    captured = {}

    def fake_llm(messages, **kwargs):
        captured["prompt"] = " ".join(m["content"] for m in messages)
        return "thrifted this and i'm obsessed #ootd"

    monkeypatch.setattr(tools, "_llm", fake_llm)
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("paired with baggy jeans", item)
    assert isinstance(card, str) and card.strip()
    # The item name and platform should be handed to the model.
    assert item["title"] in captured["prompt"]
    assert item["platform"] in captured["prompt"]
