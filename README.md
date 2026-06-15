# FitFindr 🛍️

A multi-tool AI agent that helps you find secondhand clothing and figure out how
to wear it. Give it one natural-language request and a wardrobe; it searches a
mock listings dataset, suggests how to style the best match against pieces you
already own, and writes a shareable "fit card" caption — in a single pass.

```
User query ──► run_agent() ──► search_listings ──► suggest_outfit ──► create_fit_card ──► session
                                     │
                                     └─ no matches ──► error message, stop early
```

---

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash);  use .venv\Scripts\activate on cmd
pip install -r requirements.txt
```

Create a `.env` file in the repo root (already in `.gitignore` — never commit it):

```
GROQ_API_KEY=your_key_here
```

Free key at [console.groq.com](https://console.groq.com). The LLM-backed tools use
Groq's `llama-3.3-70b-versatile`.

## Run

```bash
python app.py          # Gradio UI — open the URL it prints (usually http://localhost:7860)
python agent.py        # CLI: happy-path + no-results demo
pytest tests/          # 20 unit tests, run offline (LLM calls are mocked)
```

---

## Tool Inventory

All tool signatures live in [`tools.py`](tools.py). Tool 1 is pure Python
(deterministic); Tools 2 and 3 call the Groq LLM.

### `search_listings(description, size, max_price) -> list[dict]`
- **Inputs:**
  - `description` (str) — keywords describing the item (e.g. `"vintage graphic tee"`).
  - `size` (str | None) — size to filter by, or `None` to skip.
  - `max_price` (float | None) — inclusive price ceiling, or `None` to skip.
- **Output:** a list of full listing dicts (`id`, `title`, `description`,
  `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`,
  `platform`), sorted by keyword-overlap relevance. Returns `[]` — never `None` —
  when nothing matches.
- **Purpose:** filter the 40-item dataset by size and price, then rank by how many
  description keywords overlap the listing's title/description/tags/category.
  Size matching is token-based and case-insensitive, so `"M"` matches `"S/M"` and
  `"8"` matches `"W8 L30"`.

### `suggest_outfit(new_item, wardrobe) -> str`
- **Inputs:**
  - `new_item` (dict) — a listing dict from `search_listings`.
  - `wardrobe` (dict) — a wardrobe in `data/wardrobe_schema.json` format: a dict
    with an `items` list, each item having `id`, `name`, `category`, `colors`,
    `style_tags`, `notes`.
- **Output:** a non-empty styling string. With a populated wardrobe it names
  specific owned pieces; with an empty wardrobe it gives general styling advice.
- **Purpose:** explain how to wear the found item. The prompt instructs the model
  to build outfits **only** from the new item plus pieces the user actually owns.

### `create_fit_card(outfit, new_item) -> str`
- **Inputs:**
  - `outfit` (str) — the styling string from `suggest_outfit`.
  - `new_item` (dict) — the listing dict (used for name, price, platform).
- **Output:** a 2–4 sentence Instagram/TikTok-style caption + hashtags. Returns a
  descriptive error string if `outfit` is empty.
- **Purpose:** turn the outfit into something share-worthy. Runs at temperature
  0.9 so different outfits produce different captions.

---

## How the Planning Loop Works

`run_agent(query, wardrobe)` in [`agent.py`](agent.py) is a single-shot pipeline
with one conditional branch. It does **not** call all three tools unconditionally
— the no-results branch short-circuits before the LLM tools ever run.

1. **Initialize** a fresh `session` dict (`_new_session`).
2. **Parse** the query with `_parse_query` (regex) into `description`, `size`,
   `max_price`; store under `session["parsed"]`.
3. **Search** — `search_listings(...)` → `session["search_results"]`.
   - **Branch:** if the result is `[]`, set `session["error"]` to a helpful retry
     message and **return early**. `suggest_outfit` is never called on empty input.
4. **Select** the top result → `session["selected_item"]`.
5. **Suggest** — `suggest_outfit(selected_item, wardrobe)` → `session["outfit_suggestion"]`.
6. **Fit card** — `create_fit_card(outfit_suggestion, selected_item)` → `session["fit_card"]`.
7. **Return** the session.

The agent's behaviour changes with the input: an impossible query stops at step 3
with an error and `fit_card == None`; a matchable query flows through all three
tools. This branch is verified by `test_run_agent_no_results_sets_error_and_stops`
and `test_run_agent_does_not_call_llm_on_no_results`.

**Query parsing choice:** parsing is done with regex, not the LLM — it's
deterministic, fast, and free, which keeps behaviour predictable and testable.
`max_price` comes from `under/below/max $N` or a bare `$N`; `size` from an explicit
`size X` or a deliberate standalone uppercase token (matching on original case so
the `m` in "I'm" is not mistaken for size M); the matched spans are stripped from
the description before searching.

---

## State Management

Everything for a run lives in one `session` dict, built by `_new_session` and
returned to the caller. Each step reads its inputs from the session rather than
re-parsing the query, so nothing is recomputed and the data path is traceable.

| Key | Type | Set by | Used by |
|-----|------|--------|---------|
| `query` | str | `_new_session` | parser, output |
| `parsed` | dict | step 2 | `search_listings` |
| `search_results` | list[dict] | step 3 | item selection |
| `selected_item` | dict \| None | step 4 | `suggest_outfit`, `create_fit_card`, output |
| `wardrobe` | dict | caller | `suggest_outfit` |
| `outfit_suggestion` | str \| None | step 5 | `create_fit_card`, output |
| `fit_card` | str \| None | step 6 | output |
| `error` | str \| None | step 3 (no results) | UI / caller |

The item found by `search_listings` flows into `suggest_outfit` and
`create_fit_card` without the user re-entering anything. The test
`test_run_agent_happy_path_populates_session` asserts
`session["selected_item"] is session["search_results"][0]` — i.e. the exact same
object is threaded through, not a copy or a re-fetch.

---

## Error Handling Strategy

Each tool owns its failure mode — none crash the agent or fail silently.

| Tool | Failure mode | Response |
|------|--------------|----------|
| `search_listings` | no listing matches | returns `[]`; the loop sets `session["error"]` = *"I couldn't find anything that matches those exact requirements — try a slightly higher budget, a different size, or a similar style."* and returns early |
| `suggest_outfit` | empty wardrobe | returns general styling advice for the item instead of named combinations — always a non-empty string |
| `create_fit_card` | empty/whitespace `outfit` | skips the LLM and returns *"I don't have enough outfit details to generate a fit card…"* |
| LLM tools | missing `GROQ_API_KEY` | `_get_groq_client` raises a clear `ValueError` pointing at `.env` |

**Concrete example (from testing).** Running the deliberate no-results query:

```
$ python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
[]
```

and through the full agent, `session["error"]` is set, `session["fit_card"]` stays
`None`, and the Gradio UI shows the retry message in the first panel with the
outfit/fit-card panels empty — no exception, no broken card.

---

## Spec Reflection

**One way the spec helped:** writing the full tool I/O contracts and the planning
loop branches in `planning.md` *before* coding meant each tool had an unambiguous
signature and failure mode to implement against. The no-results early-exit, in
particular, was a design decision made on paper — so the implementation never had
to be retrofitted to avoid calling `suggest_outfit` on empty input.

**One way implementation diverged:** my first draft of `planning.md` described a
multi-turn conversational agent (asking the user for size/wardrobe mid-chat, tools
returning structured dicts, fields named `tags`). The actual starter is
**single-shot** — `run_agent(query, wardrobe)` returns one session, the Gradio UI
submits once, the LLM tools return strings, and the data uses `style_tags` with
the wardrobe wrapped in `{"items": [...]}`. I diverged to match the starter's real
signatures and data schema (so the code actually runs against the provided files)
and updated `planning.md` to document the single-shot design. I also fixed a parser
bug the spec surfaced while testing: a bare-letter size fallback read the `m` in
"I'm" as size `M`, so the fallback now requires an explicit `size X` or an
intentional uppercase token.

---

## AI Usage

**1 — Implementing `search_listings` from the Tool 1 spec.** I gave the AI the
Tool 1 block from `planning.md` (inputs, return schema, failure mode) plus the real
dataset field names, and asked for a pure-Python filter using `load_listings()`.
I revised the generated code: the first version did exact, case-sensitive size
equality, which failed `"M"` against `"S/M"`; I changed it to token-based,
case-insensitive matching and added stopword stripping so filler words ("under",
"size") don't pollute keyword scoring.

**2 — Implementing the planning loop from the diagram + Planning Loop / State
Management sections.** I gave the AI those sections and the architecture diagram
and asked for `run_agent` and `_parse_query`. I overrode two things: (a) the
generated parser had the "I'm" → size `M` bug, which I fixed by matching the
uppercase fallback on the original (non-lowercased) text; and (b) I made the
no-results branch return *before* selecting an item or calling any LLM tool, and
added tests (`test_run_agent_does_not_call_llm_on_no_results`) to lock that in.

---

## Demo

`python app.py`, then try the example queries (a working one like *"vintage
graphic tee under $30"* and the deliberate no-results case *"designer ballgown
size XXS under $5"*). The three panels show the listing, the outfit, and the fit
card; the no-results query routes its message into the first panel.

## Project Layout

```
├── data/                  # listings.json (40 listings) + wardrobe_schema.json
├── utils/data_loader.py   # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tools.py               # the 3 tools + shared LLM/tokenizer helpers
├── agent.py               # run_agent() planning loop + _parse_query()
├── app.py                 # Gradio UI (handle_query maps session → 3 panels)
├── tests/                 # pytest suite (test_tools.py, test_agent.py)
├── planning.md            # the design spec
└── README.md
```
