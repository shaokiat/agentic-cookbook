from common import about_from, single_run_page

CORE_CONCEPT = """\
**What it is**

Two resilience layers sit around flaky tools. A retry decorator retries the raw function with
exponential backoff, so transient failures (a dropped connection, a momentary rate limit) never
even reach the agent — they're invisible unless every retry is exhausted. If retries *are*
exhausted, the error becomes a plain string returned as an ordinary tool observation, not an
exception — letting the agent reason around it, fall back to cached data, or give a degraded
answer instead of the whole turn crashing.

```mermaid
flowchart TD
    C[Tool called] --> T{Succeeds?}
    T -->|Yes| Ok[Result added as observation]
    T -->|No, transient| B["Exponential backoff, retry"]
    B --> T
    T -->|No, retries exhausted| E["Error string added as observation — not raised"]
    E --> R[Agent reasons around the failure]
```

**Key insight**

Returning a descriptive error string always beats raising out of a tool: the agent can act on a
string — retry differently, ask the user, fall back — but an uncaught exception just crashes
the turn with no chance for the model to respond.
"""


single_run_page(
    "Error Recovery",
    "Flaky tools with retry + backoff; unrecoverable errors become observations the agent reasons around.",
    "examples/04_tool_use_patterns/03_error_recovery.py",
    about_extra=about_from(CORE_CONCEPT),
)
