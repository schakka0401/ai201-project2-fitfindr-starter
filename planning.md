# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Using the 3 parameters, it returns a list of listings which are most relevant to the requirements. It filters a hardcoded JSON dataset by size and price, then ranks what's left by how well the description matches each listing's title and style tags. No LLM here — it's plain Python so the results are predictable.

**Input parameters:**
- `description` (str): A short description of the product you want for context (e.g. "vintage graphic tee"). Used to rank listings by keyword overlap.
- `size` (str): The size of the product you want; could be shoe size, shirt size, pant measurements, etc. Matching is flexible — "M" also matches a listing labelled "S/M". Pass nothing/None to skip the size filter.
- `max_price` (float): This sets a price boundary for the product you are asking for. Listings above this price are dropped. Pass None to skip the price filter.

**What it returns:**
A list of listing dicts, each with the full item details: `id`, `title`, `price`, `size`, `style_tags`, `condition`, `colors`, `brand`, `platform`, and `description`. So the agent gets the item name, the cost, and the size (plus everything else it needs for the next tools). The list is sorted most-relevant first, and it's an empty list `[]` — not None — if nothing matches.

**What happens if it fails or returns nothing:**
When this failure case happens, it should not hallucinate a fake listing. The agent stops the pipeline right there, sets an error on the session, and tells the user something like: "I couldn't find the right item that fits your requirements — would you like to try a higher budget, a different size, or a similar style?" It does NOT call suggest_outfit on an empty result.

---

### Tool 2: suggest_outfit

**What it does:**
Based off your wardrobe, suggest_outfit will recommend how the new item fits into an outfit with the products you already own. For example, say I have a pair of sweatpants and a Young LA Hoodie — the agent would call suggest_outfit and come back with something like "A pair of Sambas would elevate this to a whole new level," along with the reasoning for why those pieces work together. It uses the LLM (Groq, llama-3.3-70b-versatile) and is told to only style with pieces I actually own.

**Input parameters:**
- `new_item` (dict): The listing the agent just found in search_listings — the piece we're building the outfit around.
- `wardrobe` (dict): The items you already own. This is a dict with an `items` list, where each item has a `name`, `category`, `colors`, `style_tags`, and optional `notes`.

**What it returns:**
A string with a convincing description of how the new item complements your wardrobe, naming the specific pieces it pairs with. It's always a non-empty string.

**What happens if it fails or returns nothing:**
If the wardrobe is empty (no items), it doesn't crash or skip — it falls back to general styling advice for the item on its own (what colors, categories, and occasions suit it). So the user always gets something useful back.

---

### Tool 3: create_fit_card

**What it does:**
Takes the outfit and turns it into a short, shareable caption — the kind of thing you'd actually post under an Instagram/TikTok OOTD, not a product blurb. It runs the LLM at a high temperature so different outfits come out sounding different.

**Input parameters:**
- `outfit` (str): The outfit suggestion string that came out of suggest_outfit.
- `new_item` (dict): The listing dict, so the caption can name the item, its price, and the platform it's from.

**What it returns:**
A 2–4 sentence caption string that mentions the item name, price, and platform naturally, captures the vibe, and ends with 4–6 style hashtags.

**What happens if it fails or returns nothing:**
If the outfit string is empty or blank, it does NOT call the LLM and does NOT crash. It returns a clear message instead — "I don't have enough outfit details to generate a fit card — let me re-run the outfit suggestion first." — so the agent never hands back a broken card.

---

### Additional Tools (if any)

None — the agent uses the three required tools above.

---

## Planning Loop

**How does your agent decide which tool to call next?**

It's a single-shot pipeline with one decision point. The agent takes the query and the wardrobe up front (no back-and-forth chat), then runs in order — but it only continues if the previous step gave it something to work with.

1. Start a fresh `session` dict to hold everything.
2. Parse the query with regex to pull out `description`, `size`, and `max_price`. (I chose regex over the LLM because parsing should be deterministic, fast, and free.)
3. Call `search_listings`. **This is the decision point:** if it returns `[]`, set `session["error"]` and stop — don't call the other tools. If it returns matches, keep going.
4. Pick the top result as `session["selected_item"]`.
5. Call `suggest_outfit(selected_item, wardrobe)` and save the result.
6. Call `create_fit_card(outfit, selected_item)` and save the result.
7. Return the session.

The behavior changes based on what comes back: an impossible query stops at step 3 with an error and never touches the LLM; a good query flows all the way to a fit card. It's done when the session is returned.

---

## State Management

**How does information from one tool get passed to the next?**

Everything lives in one `session` dict that's created at the start of the run and passed down through each step. Each tool reads what it needs from the session instead of re-asking the user, so the item found by search_listings flows straight into suggest_outfit and create_fit_card — it's the exact same dict, no re-entry.

| Key | Type | Set by | Used by |
|-----|------|--------|---------|
| `query` | str | start of run | parser, output |
| `parsed` | dict | step 2 (regex parse) | search_listings |
| `search_results` | list[dict] | search_listings | picking the top item |
| `selected_item` | dict / None | step 4 (top result) | suggest_outfit, create_fit_card, output |
| `wardrobe` | dict | passed in by the caller | suggest_outfit |
| `outfit_suggestion` | str / None | suggest_outfit | create_fit_card, output |
| `fit_card` | str / None | create_fit_card | output |
| `error` | str / None | search_listings (no results) | UI / caller |

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Returns `[]`. The loop sets `session["error"]` ("I couldn't find anything that matches those exact requirements — try a slightly higher budget, a different size, or a similar style") and stops early. suggest_outfit is never called on empty input. |
| suggest_outfit | Wardrobe is empty | Doesn't crash — falls back to general styling advice for the item on its own. Always returns a non-empty string. |
| create_fit_card | Outfit input is missing or incomplete | Skips the LLM entirely and returns "I don't have enough outfit details to generate a fit card — let me re-run the outfit suggestion first." No exception, no broken card. |

---

## Architecture

```
User query ("vintage graphic tee under $30")  +  wardrobe
    │
    ▼
run_agent(query, wardrobe)
    │
    ├─► new session dict            (holds all state for this run)
    │
    ├─► parse query (regex)  ─►  session["parsed"] = {description, size, max_price}
    │
    ├─► search_listings(description, size, max_price)
    │       │
    │       ├── results = []  ──►  session["error"] = "couldn't find anything..."
    │       │                       return session            ◄── ERROR PATH (stop)
    │       │
    │       └── results = [item, ...]  ──►  session["selected_item"] = results[0]
    │                                            │
    ├─► suggest_outfit(selected_item, wardrobe) ◄┘
    │       │
    │       ├── wardrobe empty   ──► general styling advice
    │       └── wardrobe present ──► outfit using owned pieces
    │              └─►  session["outfit_suggestion"] = "..."
    │
    ├─► create_fit_card(outfit_suggestion, selected_item)
    │       │
    │       ├── outfit empty ──► error-message string (no LLM call)
    │       └── outfit ok    ──► caption + hashtags
    │              └─►  session["fit_card"] = "..."
    │
    └─► return session   (error=None; selected_item, outfit_suggestion, fit_card all set)
            │
            ▼
    app.py handle_query  ─►  3 Gradio panels (listing | outfit | fit card)
                              error routes into the first panel
```

---

## AI Tool Plan

For each part of the implementation below: which AI tool, what I give it, what I expect back, and how I verify it before trusting it.

**Milestone 3 — Individual tool implementations:**

- **search_listings:** I'll give Claude the Tool 1 block (inputs, return value, failure mode) plus the real dataset field names, and ask it to implement the function using `load_listings()`. Before trusting it I'll check it filters by all three parameters, returns the full listing dicts, returns `[]` (not None) on no match, and that "M" matches "S/M". I'll test it with a query that matches, one where size filters everything out, and one where price does.
- **suggest_outfit:** I'll give Claude the Tool 2 block and the wardrobe schema and ask it to branch on an empty wardrobe (general advice) vs. a populated one (outfits from owned pieces), always returning a non-empty string. I'll verify the empty-wardrobe case doesn't crash and the normal case names real pieces.
- **create_fit_card:** I'll give Claude the Tool 3 block and ask it to guard an empty outfit (return a message, don't crash), then call the LLM at high temperature. I'll verify the guard works and that two different outfits give two different captions.

**Milestone 4 — Planning loop and state management:**

I'll give Claude the Planning Loop section, the State Management table, and the diagram above, and ask it to implement `run_agent(query, wardrobe)` plus the regex query parser, following the early-exit logic exactly. Before running it end-to-end I'll verify: the session starts with every key, the no-results path sets the error and returns without calling the LLM tools, and `selected_item` is always set before suggest_outfit runs. The walkthrough below is my integration test.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The loop parses the query with regex and pulls out `description="vintage graphic tee"`, `size=None`, `max_price=30.0` (the "baggy jeans and chunky sneakers" part is covered by the wardrobe, which is supplied separately — here the example wardrobe, which already contains baggy jeans and chunky sneakers). It calls `search_listings("vintage graphic tee", None, 30.0)`.

**Step 2:**
search_listings filters to items ≤ $30 and ranks by keyword overlap. The top result is the Y2K Baby Tee — Butterfly Print (`lst_002`, $18.00, size S/M, depop). The agent stores it as `session["selected_item"]`. (If nothing had matched, it would stop here with an error instead.)

**Step 3:**
The agent calls `suggest_outfit(selected_item, wardrobe)`. The wardrobe isn't empty, so it returns named combinations — e.g. pairing the tee with the baggy straight-leg jeans and chunky white sneakers for a streetwear look, or dressing it up with the wide-leg khaki trousers and the vintage black denim jacket. This goes into `session["outfit_suggestion"]`.

**Step 4:**
The agent calls `create_fit_card(outfit_suggestion, selected_item)`, which returns a caption like: "Just thrifted this Y2K butterfly baby tee off depop for $18 and it was made for my baggy jeans 🦋 #y2k #thriftfinds #ootd #streetwear #depop". This goes into `session["fit_card"]`.

**Final output to user:**
```
🛍 Found for you:
Y2K Baby Tee — Butterfly Print | $18.00 · size S/M · excellent | depop

👕 How to wear it:
Pair it with your baggy straight-leg jeans and chunky white sneakers for an easy
streetwear look, or dress it up with the wide-leg khaki trousers and your vintage
black denim jacket on top.

📸 Fit card:
"Just thrifted this Y2K butterfly baby tee off depop for $18 and it was made for
my baggy jeans 🦋"
#y2k #thriftfinds #ootd #streetwear #depop
```

If the query had been impossible (e.g. "designer ballgown size XXS under $5"), search_listings would return `[]`, the agent would set `session["error"]` with the "couldn't find anything" message, and stop — the outfit and fit-card panels would stay empty.
