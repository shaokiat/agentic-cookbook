# LLM Provider Strategies: How Production Agent Systems Call Models

This document compares three approaches to LLM provider integration found across the reference implementations in this cookbook — a thin proxy library (`litellm` in `core/`), a hand-rolled Python plugin system (nanobot), and a custom TypeScript library (pi-mono, consumed by openclaw). Each approach reflects a different set of constraints, and choosing the wrong one creates friction that compounds as the system grows.

---

## The Core Problem

Every agent loop reduces to: assemble messages, call a model, handle tool calls, repeat. The interesting engineering question is _who owns the translation layer_ between your agent's internal message format and each provider's wire format. Your answer determines how much control you have over prompt caching, streaming, retry logic, and provider-specific features like Anthropic's extended thinking.

---

## Approach 1: LiteLLM Proxy (`core/model.py`)

`core/model.py` calls `litellm.completion()` directly. LiteLLM is a Python library that exposes a single OpenAI-compatible interface and routes to 100+ providers internally.

```python
# core/model.py
import litellm

response = litellm.completion(
    model=self.model,   # e.g. "anthropic/claude-sonnet-4-6"
    messages=messages,
    tools=tools,
)
cost = litellm.completion_cost(completion_response=response)
```

The provider is selected by a model string prefix (`anthropic/`, `openai/`, `bedrock/`). Switching providers is a config change, not a code change.

### Pros

- **Minimal setup.** One import, one function call. No provider-specific code to write or maintain.
- **Provider portability.** Swapping from `anthropic/claude-sonnet-4-6` to `openai/gpt-4o` requires changing one string.
- **Built-in cost tracking.** `litellm.completion_cost()` works across all providers without extra instrumentation.
- **Right for prototyping.** When the goal is teaching agent patterns (tool loops, orchestration), the LLM call is intentionally kept boring.

### Cons

- **Provider features lag.** LiteLLM normalises everything to the OpenAI response shape. Anthropic-native features like `thinking_blocks`, fine-grained cache headers, and `interleaved-thinking` betas either aren't exposed or require workarounds.
- **Retry and streaming are opaque.** You get what LiteLLM gives you. Customising backoff strategy or streaming behaviour requires patching or wrapping the library.
- **No streaming-native design.** `litellm.completion()` returns a complete response. Streaming requires a separate `stream=True` path that returns a different object type, making the agent loop asymmetric.
- **Black-box error handling.** Provider-specific error codes (rate limit headers, region-specific failures) are collapsed into LiteLLM's generic exceptions.

**When to use it:** Early prototyping, multi-provider benchmarking, examples where the LLM call is not the interesting part.

---

## Approach 2: Custom Provider Plugin System (nanobot — `research/nanobot/`)

Nanobot defines an abstract `LLMProvider` base class (`nanobot/providers/base.py`) and implements a separate class for each provider backend. The `AgentRunner` (`nanobot/agent/runner.py`) depends only on the `LLMProvider` interface — it never imports an SDK directly.

```python
# nanobot/providers/anthropic_provider.py
from anthropic import AsyncAnthropic

class AnthropicProvider(LLMProvider):
    def __init__(self, ...):
        self._client = AsyncAnthropic(...)

    async def chat_with_retry(self, messages, tools, model, ...):
        # Full control: cache headers, thinking params, retry policy
        ...
```

The factory (`nanobot/providers/factory.py`) reads config and instantiates the right provider. `AgentRunner.run()` calls `self.provider.chat_with_retry()` or `self.provider.chat_stream_with_retry()` depending on whether the hook requests streaming.

Provider backends currently implemented: `anthropic_provider.py`, `openai_compat_provider.py`, `azure_openai_provider.py`, `github_copilot_provider.py`, `openai_codex_provider.py`.

### Pros

- **Full access to provider-native features.** `AnthropicProvider` can set `thinking_blocks`, `reasoning_content`, interleaved thinking betas, and per-message cache breakpoints — none of which LiteLLM exposes cleanly.
- **Centralised retry logic.** `LLMProvider._run_with_retry()` in `base.py` handles rate-limit backoff, timeout recovery, and the `provider_retry_mode` config flag uniformly across all providers.
- **Streaming is first-class.** `chat_stream_with_retry()` streams via `on_content_delta` callbacks and integrates with the hook system, letting the agent runner drive streaming and non-streaming paths with the same loop logic.
- **Clean seam for testing.** The `AgentRunner` accepts any `LLMProvider` — injecting a fake provider for unit tests is trivial.

### Cons

- **Each new provider requires a new class.** Adding support for a new provider means implementing the full interface: message format translation, error handling, streaming, usage parsing. This is engineering work, not config.
- **Message format translation is repeated.** Every provider needs to handle OpenAI-to-Anthropic message conversion, tool schema normalisation, and system message extraction. There is some shared code but the pattern is implemented per-provider.
- **Python-only.** The abstraction is language-specific. A TypeScript client or mobile SDK cannot reuse it.

**When to use it:** Production Python agents that need deep control over a small number of providers, especially when Anthropic-native features (extended thinking, prompt caching) are non-negotiable.

---

## Approach 3: Custom TypeScript LLM Library (pi-mono — `research/pi-mono/`)

Pi-mono ships a standalone TypeScript package `@mariozechner/pi-ai` (`packages/ai/`) that openclaw consumes as a dependency. It uses a provider registry pattern: each provider file registers itself at import time, and the public API is just `stream(model, context)` / `complete(model, context)`.

```typescript
// packages/ai/src/stream.ts
export function stream<TApi extends Api>(
  model: Model<TApi>,
  context: Context,
  options?: ProviderStreamOptions,
): AssistantMessageEventStream {
  const provider = resolveApiProvider(model.api);
  return provider.stream(model, context, options);
}
```

Each provider imports its SDK directly:

```typescript
// packages/ai/src/providers/anthropic.ts
import Anthropic from "@anthropic-ai/sdk";

// registers under api = "anthropic-messages"
// handles: prompt caching, extended thinking, betas, streaming, tool calls
```

Openclaw's `extensions/anthropic/stream-wrappers.ts` wraps `streamSimple` from `@mariozechner/pi-ai` and adds openclaw-specific policy layers (fast mode, service tier, beta header composition).

Provider backends: `anthropic.ts`, `openai-responses.ts`, `openai-completions.ts`, `google.ts`, `google-vertex.ts`, `amazon-bedrock.ts`, `mistral.ts`, `cloudflare.ts`, `github-copilot-headers.ts`, and more — 15+ total.

### Pros

- **Reusable across products.** The library is a separate package. Openclaw, pi-mono's TUI (`packages/tui`), and the web UI (`packages/web-ui`) all consume it. One implementation, multiple consumers.
- **Typed model registry.** `Model<TApi>` is a discriminated generic — the TypeScript compiler enforces that Anthropic-specific options are only passed to Anthropic models. Provider mismatches are caught at compile time, not runtime.
- **Streaming as the primary interface.** `stream()` returns an `AssistantMessageEventStream` — an async event emitter. `complete()` is sugar over `stream().result()`. The whole library is designed around streaming, not retrofitted onto it.
- **Layered extension points.** Openclaw adds its own wrappers (`createAnthropicFastModeWrapper`, `createAnthropicServiceTierWrapper`) without modifying the core library. Provider behaviour is composed at the call site, not baked in.
- **Prompt caching handled natively.** `anthropic.ts` resolves `CacheRetention` per message and attaches `cache_control` headers deterministically — a hard requirement for cost-efficient production deployments.

### Cons

- **Highest upfront investment.** Building and maintaining a multi-provider TypeScript library is a significant engineering commitment. It only pays off when you have multiple consumers or a long-lived product.
- **TypeScript-only.** Python agents cannot use it without a binding layer or a duplicate implementation.
- **Discovery complexity.** The provider registry means providers self-register at import time via side effects (`register-builtins.ts`). This is a common TypeScript pattern but can surprise newcomers and create subtle ordering dependencies.
- **Versioning burden.** Because `@mariozechner/pi-ai` is a shared package, breaking changes require coordinated updates across all consumers.

**When to use it:** Long-lived TypeScript products with multiple frontends that all need LLM access, where prompt caching and provider-native features are required from day one.

---

## Side-by-Side Comparison

| Property                      | `core/` (litellm)           | nanobot (provider plugins) | pi-mono (custom library)     |
| :---------------------------- | :-------------------------- | :------------------------- | :--------------------------- |
| **Language**                  | Python                      | Python                     | TypeScript                   |
| **Provider support**          | 100+ via proxy              | ~5, each hand-written      | 15+, each hand-written       |
| **Setup cost**                | Minimal                     | Medium                     | High                         |
| **Anthropic-native features** | Partial (via LiteLLM gaps)  | Full                       | Full                         |
| **Prompt caching control**    | Limited                     | Per-message headers        | Per-message, typed           |
| **Extended thinking**         | Not exposed cleanly         | `thinking_blocks` native   | `ThinkingLevel` typed enum   |
| **Streaming design**          | Retrofitted (`stream=True`) | First-class via callbacks  | First-class via event stream |
| **Retry/backoff ownership**   | LiteLLM's policy            | Custom per-provider        | Custom per-provider          |
| **Testability**               | Mock `litellm.completion`   | Inject `LLMProvider`       | Inject registered provider   |
| **Reusability**               | Any Python project          | Single-app Python          | Shared TS package            |
| **Right for**                 | Prototypes, teaching        | Production Python agents   | Production TS products       |

---

## The Design Divergence That Matters

All three systems converge on the same insight: **the agent loop should not know which provider it is talking to.** `AgentRunner` in nanobot accepts `LLMProvider`; openclaw's agent runner calls `streamSimple` from `@mariozechner/pi-ai`; even `core/ModelProvider` wraps `litellm.completion` behind a `generate()` method.

The divergence is in _where the translation layer lives and who owns it_. LiteLLM externalises it to a third-party library. Nanobot owns it internally per-provider class. Pi-mono extracts it into a first-party shared package.

The cost of externalising (litellm) is that you get only what the proxy exposes. The cost of owning it internally (nanobot, pi-mono) is that you must maintain message format translation, error handling, and streaming for every provider you support. The cost of sharing it as a package (pi-mono) is coordinated versioning across consumers — but that cost is paid once, not once per product.

For the examples in `core/`, litellm is the right call: the interesting code is the agent loop, not the provider adapter. For production deployments where prompt caching and extended thinking directly affect latency and cost, the nanobot or pi-mono approach is the correct baseline.

---

_See also_: `docs/reference_architectures.md` for full architectural analysis of openclaw and nanobot.
