"""
Tests for the planning loop and query parser in agent.py.

The no-results branch is tested for real (it never reaches the LLM). The happy
path monkeypatches the LLM call so it runs offline and deterministically while
still exercising the real control flow and state passing.

Run from the repo root:  pytest tests/
"""

import tools
from agent import run_agent, _parse_query
from utils.data_loader import get_example_wardrobe


# ── query parsing ───────────────────────────────────────────────────────────

def test_parse_extracts_price():
    parsed = _parse_query("vintage graphic tee under $30")
    assert parsed["max_price"] == 30.0


def test_parse_extracts_explicit_size():
    parsed = _parse_query("black combat boots size 8")
    assert parsed["size"] == "8"
    assert parsed["max_price"] is None


def test_parse_uppercase_size_fallback():
    parsed = _parse_query("90s track jacket in M")
    assert parsed["size"] == "M"


def test_parse_ignores_lowercase_contraction():
    # The "m" in "I'm" must NOT be read as size M.
    parsed = _parse_query("I'm looking for a flowy midi skirt under $40")
    assert parsed["size"] is None
    assert parsed["max_price"] == 40.0


def test_parse_cleans_description():
    parsed = _parse_query("vintage graphic tee under $30, size M")
    assert "$30" not in parsed["description"]
    assert "size" not in parsed["description"].lower()
    assert "vintage" in parsed["description"]


# ── planning loop ───────────────────────────────────────────────────────────

def test_run_agent_no_results_sets_error_and_stops():
    session = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())
    assert session["error"] is not None
    # The agent must NOT have called the downstream tools.
    assert session["selected_item"] is None
    assert session["outfit_suggestion"] is None
    assert session["fit_card"] is None


def test_run_agent_happy_path_populates_session(monkeypatch):
    monkeypatch.setattr(tools, "_llm", lambda *a, **k: "mock llm text")
    session = run_agent("vintage graphic tee under $30", get_example_wardrobe())

    assert session["error"] is None
    assert session["selected_item"] is not None
    assert session["search_results"], "expected non-empty search results"
    # State passing: the selected item is exactly the top search result.
    assert session["selected_item"] is session["search_results"][0]
    assert session["outfit_suggestion"] == "mock llm text"
    assert session["fit_card"] == "mock llm text"


def test_run_agent_does_not_call_llm_on_no_results(monkeypatch):
    # If the LLM is touched on the no-results path, this blows up the test.
    def boom(*a, **k):
        raise AssertionError("LLM must not be called when search returns nothing")

    monkeypatch.setattr(tools, "_llm", boom)
    session = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())
    assert session["error"] is not None
