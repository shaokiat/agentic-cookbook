# State Store — Deep Dive

This document explains the state store implementation in detail: what it stores, why each field was chosen, how the data flows through the program, how the interactive position update works, how structured session records are extracted via a distillation API call, and the reasoning behind the design decisions. It is written for a software engineer reading the code for the first time, or reviewing it in preparation for a technical discussion.

---

## What problem it solves

Without a state store, every session starts from scratch. The user is asked for their current position on every run, and Claude has no memory that it already analysed this ticker last week — what it concluded, what strategy it suggested, what the stock was trading at, or whether the thesis turned out to be right.

The state store gives theta-agent two forms of cross-session memory:

1. **Position persistence** — the user's holdings in the ticker survive between sessions. They enter it once; on the next run they see it pre-filled and can keep, update, or clear it.
2. **Session history** — a structured record of what was found and recommended in past sessions. The most recent entries are formatted and injected into the research prompt so Claude can frame its new analysis in relation to what it said before.

---

## What is stored per session and why

Each session record is a structured dict, not a free-text blob. The fields were chosen to answer a specific question that arises on the *next* visit to the same ticker.

| Field | Type | Answers |
|---|---|---|
| `date` | YYYY-MM-DD string | When was this analysis done? |
| `price_at_analysis` | float | What was the stock trading at? How much has it moved since? |
| `directional_bias` | "bullish" \| "bearish" \| "neutral" | What was the call last time? Was it right? |
| `thesis` | string | *Why* was the bias what it was, in one sentence? |
| `strategy_name` | string | What strategy family was recommended? |
| `trade` | string | Exact contracts — is this position still open? |
| `max_profit` / `max_loss` | string | What was the risk profile of that trade? |
| `breakeven` | string | Where did the stock need to be? |
| `iv_environment` | "low" \| "high" \| "unknown" | Was IV a factor in strategy selection? Is it different now? |
| `key_themes` | list of strings | What news or data drove the thesis? Are those themes still in play? |
| `outcome` | string \| null | Was the trade profitable? (Null at save time; user fills in manually.) |

A free-text summary would require Claude to re-parse prose on every future session to extract any of these. A structured record means `prior_context()` can format each field precisely and Claude can compare values directly — e.g. "price was $178 last time, it's now $195, the bull call spread breakeven was $182.50, so the position would be profitable."

---

## File layout

```
theta/state.py          ← module with load(), save(), prior_context()
state/                  ← auto-created on first save()
└── AAPL.json           ← one file per ticker, named {TICKER}.json
```

The `state/` directory does not exist until the first `save()` call. At that point `Path.mkdir(exist_ok=True)` creates it. There is one JSON file per ticker; the filename is always the ticker in uppercase.

### On-disk JSON schema

```json
{
  "ticker": "AAPL",
  "last_updated": "2026-05-09T14:30:00+00:00",
  "position": "Long 100 shares @ $178, sold 1x Jun $190 covered call",
  "sessions": [
    {
      "date": "2026-05-09",
      "price_at_analysis": 189.42,
      "directional_bias": "bullish",
      "thesis": "Bullish on product cycle momentum with IV compressed favouring long premium.",
      "strategy_name": "Bull Call Spread",
      "trade": "Buy $190 call / Sell $195 call, expiry Jun 20",
      "max_profit": "$320 per contract",
      "max_loss": "$180 per contract",
      "breakeven": "$191.80",
      "iv_environment": "low",
      "key_themes": ["analyst upgrades", "IV compressed", "product launch"],
      "outcome": null
    }
  ]
}
```

---

## Module walkthrough — `theta/state.py`

### Module-level constants

```python
_STATE_DIR = Path("state")
_MAX_SESSIONS = 10
```

`_STATE_DIR` is a relative `Path`. At runtime it resolves relative to the working directory — wherever `python theta.py` is invoked from. In normal use that is the project root, so `state/AAPL.json` resolves correctly.

`_MAX_SESSIONS = 10` is the rolling window cap. Older sessions are dropped on `save()`. The file stays bounded in size indefinitely.

---

### `_path(ticker)` — private helper

```python
def _path(ticker: str) -> Path:
    return _STATE_DIR / f"{ticker}.json"
```

A single place that constructs the file path from a ticker symbol. Both `load()` and `save()` call this rather than constructing the path inline — a future change to the directory structure or naming convention is a one-line edit.

---

### `load(ticker)` — reading state

```python
def load(ticker: str) -> dict:
    p = _path(ticker.upper())
    if p.exists():
        return json.loads(p.read_text())
    return {"ticker": ticker.upper(), "position": None, "sessions": []}
```

1. Normalises the ticker to uppercase.
2. Checks file existence with `Path.exists()`. No race condition risk — this is a single-user CLI tool with no concurrent writers.
3. If the file exists: reads with `Path.read_text()` (UTF-8 by default), deserialises with `json.loads()`.
4. If the file does not exist: returns a **blank template** with the same shape as a real state dict. This is the null object pattern — callers always receive a valid dict and never need to handle a missing-file case. `sessions` is an empty list, so `prior_context()` returns `None` and no context is injected on the first session.

---

### `save(ticker, position, record)` — writing state

```python
def save(ticker: str, position: str | None, record: dict) -> None:
    _STATE_DIR.mkdir(exist_ok=True)
    state = load(ticker)
    now = datetime.now(timezone.utc)
    state["last_updated"] = now.isoformat()
    state["position"] = position
    record.setdefault("date", now.strftime("%Y-%m-%d"))
    record.setdefault("outcome", None)
    state["sessions"].append(record)
    state["sessions"] = state["sessions"][-_MAX_SESSIONS:]
    _path(ticker.upper()).write_text(json.dumps(state, indent=2))
```

**Step by step:**

**1. Create the directory if absent.**
`mkdir(exist_ok=True)` is idempotent — does nothing if the directory exists, creates it if it doesn't. No separate "directory created" flag is needed.

**2. Read-modify-write.**
`save()` calls `load()` at the start to get the current on-disk state, modifies it in memory, then writes it back. This means `save()` is safe to call even when no file exists yet — `load()` returns the blank template and `save()` writes the file for the first time. It also means the sessions list accumulates correctly across runs.

**3. Timestamp.**
`datetime.now(timezone.utc)` produces a timezone-aware UTC datetime. `.isoformat()` serialises it unambiguously regardless of the machine's local timezone.

**4. Overwrite the position.**
`state["position"] = position` replaces whatever was stored. Position is a single mutable value — the user has one current position per ticker, and the previous value is no longer relevant once it changes.

**5. Stamp the record.**
`record.setdefault("date", ...)` and `record.setdefault("outcome", None)` fill in fields that the caller may not have set. `setdefault` only writes if the key is absent — it will not overwrite a `date` that the extraction step already placed on the record.

**6. Append and trim.**
The record is appended to the end of `sessions` (oldest-first ordering). `sessions[-_MAX_SESSIONS:]` keeps the last 10 by taking a tail slice. Python slicing on a list shorter than the cap returns the full list, so this is safe from the first save.

**7. Write.**
`Path.write_text()` truncates and rewrites the file. For a single-user CLI tool this is sufficient. A production implementation would write to a temp file then call `os.replace(tmp, target)` for atomic replacement (crash-safe).

---

### `prior_context(state, max_sessions=3)` — formatting context for injection

```python
def prior_context(state: dict, max_sessions: int = 3) -> str | None:
    sessions = state.get("sessions", [])
    if not sessions:
        return None
    recent = sessions[-max_sessions:]
    lines = ["Prior sessions (most recent first):"]
    for s in reversed(recent):
        ...
    return "\n".join(lines)
```

1. Guards on an empty list — returns `None` so callers can skip injection entirely on a first session.
2. Takes the last `max_sessions` entries with a tail slice.
3. Iterates in reverse (most recent first) — the newest context appears first in the prompt, which is more useful to Claude.
4. **Handles both formats** via a branch: legacy records (saved before this version) have a `"summary"` key with a plain string; structured records have typed fields. This backward-compatibility branch means existing state files are not broken by the schema change.
5. Returns a plain-text string, not JSON. The block is injected directly into the research prompt that Claude reads as a user message — natural language is more parseable by the model than raw JSON in this context.

**Example output for a structured record:**
```
Prior sessions (most recent first):
  2026-05-09:
    Price at analysis: $189.42
    Bias: bullish
    Thesis: Bullish on product cycle momentum with IV compressed favouring long premium.
    Strategy: Bull Call Spread
    Trade: Buy $190 call / Sell $195 call, expiry Jun 20
    Max profit: $320 per contract  |  Max loss: $180 per contract  |  Breakeven: $191.80
    IV environment: low
    Key themes: analyst upgrades, IV compressed, product launch
```

---

## How session records are extracted — the distillation call

The structured record is not built from parsing strings or hardcoded field extraction. It is produced by a dedicated API call at session end, using the full in-memory message history that already exists from Phase 1.

### Why a separate API call?

Alternatives considered:

| Approach | Problem |
|---|---|
| Parse the summary string with regex | Fragile — depends on Claude's output format never varying |
| Change Phase 1 output to return JSON | Changes the user-facing terminal output; requires a separate display step |
| Extract price from tool results in Python | Feasible for price, but strategy/bias/themes cannot be reliably extracted without NLP |
| Separate API call using existing messages | Clean, reliable, no re-fetching, model reads its own prior output |

The distillation call reuses the messages list already in memory. No yfinance calls, no new data fetched — Claude reads the tool results and its own Phase 1 summary to fill in the fields.

### The extraction prompt

```
Extract a structured session record from this research session.
Return ONLY a valid JSON object — no prose, no markdown, no explanation — with exactly these fields:

{
  "price_at_analysis": <current price as a float, from the price data tool result>,
  "directional_bias": <"bullish" | "bearish" | "neutral">,
  "strategy_name": <name of the recommended strategy>,
  "trade": <specific contracts>,
  "max_profit": <e.g. "$320 per contract">,
  "max_loss": <e.g. "$180 per contract">,
  "breakeven": <e.g. "$191.80">,
  "iv_environment": <"low" | "high" | "unknown">,
  "key_themes": <list of 2-3 short strings summarising the main drivers>,
  "thesis": <one sentence directional argument>
}

If a field cannot be determined from the session data, use null.
```

The prompt instructs the model to return only JSON with no surrounding text. `max_tokens=512` is sufficient for the compact JSON blob.

### The `_extract_session_record` method

```python
def _extract_session_record(self, messages: list) -> dict:
    try:
        extraction_messages = list(messages) + [
            {"role": "user", "content": _EXTRACTION_PROMPT}
        ]
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=extraction_messages,
        )
        raw = next(
            (block.text for block in response.content if hasattr(block, "text")),
            "{}",
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        return {}
```

**Key points:**

- `list(messages)` copies the list before appending — the extraction prompt is not visible to the user in the chat loop.
- No `system=` argument is passed. The extraction call is not a research call; the system prompt's "you are an options research assistant" framing is not needed and would add noise.
- The markdown fence stripping (`startswith("```")`) is a defence against models that occasionally wrap JSON in a code block despite being instructed not to. The fence is stripped before `json.loads()`.
- The outer `try/except Exception` catches any parsing failure and returns an empty dict. `save()` will still be called with the empty dict, and `setdefault` will fill in `date` and `outcome`. A failed extraction produces a minimal record rather than crashing the session.

### The `_save_session` helper

```python
def _save_session(self, messages: list) -> None:
    print("  [state] extracting session record...")
    record = self._extract_session_record(messages)
    state_store.save(self.ticker, self.positions, record)
    print(f"  [state] state/{self.ticker}.json updated")
```

This is the single call site shared by both exit paths (clean exit and Ctrl-C). Centralising it ensures both paths go through extraction — a copy-paste bug would have caused one path to skip extraction.

---

## How interactive state updates work

The interactive position prompt lives in `theta.py`, not `state.py`. This separation is deliberate: `state.py` is a pure persistence layer (read/write JSON), while `theta.py` owns user interaction. This keeps `state.py` testable in isolation without mocking `input()`.

### The prompt function

```python
def _prompt_position(ticker: str, stored: str | None) -> str | None:
    if stored:
        print(f"\nStored position for {ticker}: {stored}")
        print("  Press Enter to keep, type a new position to update, or 'clear' to remove:")
        raw = input("  > ").strip()
        if raw.lower() == "clear":
            return None
        return raw if raw else stored
    else:
        print(f"\nCurrent position in {ticker} (optional — press Enter to skip):")
        raw = input("  > ").strip()
        return raw if raw else None
```

The function branches on whether a stored position exists, giving users two distinct experiences:

**First-time user (no stored position):**
```
Current position in AAPL (optional — press Enter to skip):
  >
```

**Returning user (position exists):**
```
Stored position for AAPL: Long 100 shares @ $178, sold 1x Jun $190 covered call
  Press Enter to keep, type a new position to update, or 'clear' to remove:
  >
```

Three outcomes from the returning-user prompt:
- **Blank Enter** → `return raw if raw else stored` returns the unchanged stored value
- **New text** → returns the new text, replacing what was stored
- **`"clear"`** → returns `None`, which `save()` writes back as `json null`

The function returns the resolved position value and does not call `save()` itself. The returned value is held in `ThetaAgent.positions` for the duration of the session and only written to disk at exit.

---

## Full data flow

```
theta.py startup
      │
      ├─ state_store.load("AAPL")
      │       ├─ state/AAPL.json exists?  Yes → json.loads → populated dict
      │       │                           No  → blank template dict
      │       └─ returns: {ticker, position, sessions}
      │
      ├─ state_store.prior_context(stored_state)
      │       ├─ sessions empty? → return None
      │       └─ sessions present → format last 3 as plain-text → return str
      │
      ├─ _prompt_position(ticker, stored_state["position"])
      │       ├─ stored present → show, offer keep/update/clear → return resolved str|None
      │       └─ stored absent  → ask optional input → return str|None
      │
      └─ ThetaAgent(ticker, client, positions=..., prior_context=...)
                │
                ├─ run_research()
                │       ├─ builds initial_content:
                │       │     base prompt
                │       │     + "Current position: ..."      (if positions set)
                │       │     + "Prior sessions: ..."        (if prior_context set)
                │       ├─ runs tool-use loop (4 tools)
                │       └─ returns (summary, messages)       ← full history in memory
                │
                └─ chat_loop(summary, messages)
                        ├─ interactive REPL with full history as context
                        │
                        └─ on exit (exit/quit/Ctrl-C):
                                _save_session(messages)
                                  │
                                  ├─ print "[state] extracting session record..."
                                  ├─ _extract_session_record(messages)
                                  │       ├─ append _EXTRACTION_PROMPT to messages copy
                                  │       ├─ client.messages.create(max_tokens=512)
                                  │       ├─ strip markdown fences if present
                                  │       ├─ json.loads → dict
                                  │       └─ return dict (or {} on failure)
                                  │
                                  └─ state_store.save(ticker, positions, record)
                                          ├─ mkdir state/ (idempotent)
                                          ├─ load current file (read-modify-write)
                                          ├─ stamp last_updated, overwrite position
                                          ├─ setdefault date + outcome on record
                                          ├─ append record to sessions
                                          ├─ trim to last 10
                                          └─ write_text(json.dumps(..., indent=2))
```

---

## Design decisions and tradeoffs

### Structured record vs truncated summary

The previous implementation stored `session_summary[:500]` — a truncated slice of Claude's prose output. The problems with this:

- Claude must re-parse prose on future sessions to extract price, strategy, bias, etc.
- Truncation at 500 chars could cut off the strategy recommendation entirely if the summary was long
- The format is inconsistent across model versions or prompt changes

The structured record solves all three: fields are machine-extracted, no truncation of individual values, and the schema is explicit and stable.

The tradeoff is one extra API call at session end (~1–2 seconds). For a tool that already takes 15–20 seconds to run a full research cycle, this is acceptable.

### Distillation via existing messages, not re-fetch

The extraction call appends `_EXTRACTION_PROMPT` to the messages list already in memory. This means Claude is reading its own prior output and the tool results it already processed — no new yfinance calls, no extra latency beyond the API round-trip.

The alternative — building a new messages list from scratch — would require passing the raw summary text into the extraction call, losing the rich tool result context (exact price, full options chain data) that Claude uses to fill in `price_at_analysis` and `iv_environment` accurately.

### No `system=` on the extraction call

The main research calls pass `system=SYSTEM_PROMPT` which instructs Claude to format output as plain text with ALL CAPS section labels. That instruction would conflict with the extraction call's "return only JSON" instruction. Omitting `system=` gives the model a clean slate for the extraction, resulting in more reliable JSON output.

### Fallback to empty dict on extraction failure

`_extract_session_record` catches all exceptions and returns `{}`. `save()` then calls `setdefault` to fill in `date` and `outcome`, producing a minimal but valid record. The alternative — not saving at all on failure — would silently lose the session, which is worse than saving an incomplete record that at least shows the date of the session.

### Read-modify-write on every save

`save()` calls `load()` at the start. This is a full read-then-write cycle on every save. For a file this small (< 10 KB) the cost is negligible. The benefit is that `save()` always operates on the current file content, so the sessions list accumulates correctly even if something modified the file between sessions. In a single-user CLI tool there is no realistic concurrent writer, but the pattern is correct by default.

### Mutable position, append-only sessions

The position field is a single mutable value — always overwritten with the current state. The sessions list is append-only — records are never modified, only appended and trimmed. This reflects the domain: the current position is a live fact that changes; past sessions are historical records that should not be revised. The `outcome` field is the intentional exception — it starts as `null` and is meant to be filled in manually as the real-world result of the trade becomes known.

### No file locking

`Path.write_text()` does not acquire an exclusive lock. This is acceptable for a single-user CLI tool. A web-deployed or multi-user version would need `fcntl.flock` (POSIX) or a proper database with transaction semantics.

### Backward-compatible `prior_context()`

The legacy format stored `{"summary": "..."}` as a plain string. The new format stores typed fields. `prior_context()` checks for the `"summary"` key and falls back to the legacy rendering if the structured fields are absent. This means existing `state/*.json` files continue to work after upgrading — no migration script needed.
