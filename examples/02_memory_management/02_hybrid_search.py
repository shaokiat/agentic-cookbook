"""
Long-term Memory: Hybrid Search (BM25 + Vector)

Demonstrates retrieval-augmented memory — the pattern Open Claw uses in history.py.
Facts are indexed by both keyword (BM25) and semantic (vector) similarity. At query
time, only the top-k relevant facts are fetched and injected into context, rather
than everything being injected up front.

This is the key difference between intermediate memory (inject everything) and
long-term memory (retrieve what's relevant).

Docs: examples/02_memory_management/02_hybrid_search.md
"""
import os
import json
import math
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
import litellm
from rank_bm25 import BM25Okapi

from core.model import ModelProvider
from core.memory import Memory
from core.registry import ToolRegistry
from core.agent import Agent

load_dotenv()

STORE_FILE = Path(__file__).parent / "hybrid_memory_store.json"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")

BM25_WEIGHT = 0.3
VECTOR_WEIGHT = 0.7


# --- Hybrid Memory Store ---

class HybridMemoryStore:
    """
    Persistent store backed by a JSON file.

    Each entry holds the original text and its embedding vector.
    search() runs BM25 and cosine similarity in parallel and combines
    their normalised scores at BM25_WEIGHT / VECTOR_WEIGHT.
    """

    def __init__(self, path: Path = STORE_FILE):
        self.path = path
        self.entries: list[dict] = []
        self._load()

    def _load(self):
        if self.path.exists():
            self.entries = json.loads(self.path.read_text())

    def _save(self):
        self.path.write_text(json.dumps(self.entries, indent=2))

    def _embed(self, text: str) -> list[float]:
        response = litellm.embedding(model=EMBEDDING_MODEL, input=[text])
        return response.data[0]["embedding"]

    def add(self, text: str) -> None:
        embedding = self._embed(text)
        self.entries.append({
            "id": len(self.entries),
            "text": text,
            "embedding": embedding,
        })
        self._save()
        print(f"  [HybridStore] Indexed entry #{len(self.entries) - 1}: {text[:60]}")

    def search(self, query: str, top_k: int = 3) -> list[str]:
        if not self.entries:
            return []

        # BM25 — good for exact keyword matches
        corpus = [e["text"].lower().split() for e in self.entries]
        bm25 = BM25Okapi(corpus)
        bm25_raw = bm25.get_scores(query.lower().split())
        bm25_max = max(bm25_raw) if bm25_raw.max() > 0 else 1.0
        bm25_scores = bm25_raw / bm25_max  # normalize to [0, 1]

        # Vector — good for semantic / paraphrase matches
        query_emb = np.array(self._embed(query))
        stored_embs = np.array([e["embedding"] for e in self.entries])
        norms = np.linalg.norm(stored_embs, axis=1) * np.linalg.norm(query_emb)
        norms = np.where(norms == 0, 1.0, norms)
        vector_scores = (stored_embs @ query_emb) / norms  # cosine similarity

        # Hybrid combination (Open Claw: 30% BM25 + 70% vector)
        combined = BM25_WEIGHT * bm25_scores + VECTOR_WEIGHT * vector_scores
        top_indices = np.argsort(combined)[::-1][:top_k]

        print(f"  [HybridStore] Query: '{query}' → top {top_k} results:")
        for rank, i in enumerate(top_indices):
            print(f"    [{rank+1}] score={combined[i]:.3f}  bm25={bm25_scores[i]:.3f}  vec={vector_scores[i]:.3f}  | {self.entries[i]['text'][:60]}")

        return [self.entries[i]["text"] for i in top_indices]

    def __len__(self):
        return len(self.entries)


# --- Singleton store shared across sessions ---
_store = HybridMemoryStore()


# --- Tools exposed to the agent ---

def remember(fact: str) -> str:
    """Index a fact into the long-term hybrid memory store.

    :param fact: A plain-sentence fact worth remembering across sessions.
    """
    _store.add(fact)
    return f"Remembered: {fact}"


def recall(query: str) -> str:
    """Retrieve the most relevant facts from long-term memory for a query.

    :param query: A natural-language question or topic to retrieve facts about.
    """
    results = _store.search(query, top_k=3)
    if not results:
        return "No relevant facts found in long-term memory."
    bullet_list = "\n".join(f"- {r}" for r in results)
    return f"Relevant facts retrieved:\n{bullet_list}"


# --- Session factory ---

def make_agent(session_name: str, system_note: str = "") -> Agent:
    registry = ToolRegistry()
    registry.register(remember)
    registry.register(recall)

    system_prompt = (
        "You are a helpful assistant with long-term memory. "
        "Use remember() to index facts worth keeping. "
        "Use recall() to retrieve relevant facts before answering questions.\n"
        + system_note
    )
    return Agent(
        model=ModelProvider(),
        memory=Memory(),
        registry=registry,
        system_prompt=system_prompt,
        name=session_name,
    )


# --- Demo ---

def main():
    # Clear state for a clean run
    if STORE_FILE.exists():
        STORE_FILE.unlink()

    print("\n" + "=" * 60)
    print("SESSION 1: Agent indexes many facts into long-term memory")
    print("=" * 60)
    print(f"  [HybridStore] Store is empty — {len(_store)} entries\n")

    agent1 = make_agent("Session-1")
    agent1.run(
        "Please remember these facts for later:\n"
        "1. Alice is a researcher at Anthropic who specialises in interpretability.\n"
        "2. Bob is a software engineer who works on the Claude inference stack.\n"
        "3. The team's favourite programming language is Python.\n"
        "4. The project deadline is end of Q3.\n"
        "5. The main database used is PostgreSQL running on AWS RDS.\n"
        "6. Alice's preferred model for research is Claude Opus.\n"
        "7. Bob is debugging a latency regression in the embedding pipeline.\n"
        "8. The team uses GitHub Actions for CI/CD.\n"
        "9. Weekly syncs are held every Tuesday at 10am PT.\n"
        "10. The staging environment URL is staging.internal.example.com."
    )
    print(f"\n  [HybridStore] Store now has {len(_store)} indexed entries.")

    print("\n" + "=" * 60)
    print("SESSION 2: New agent retrieves only what's relevant")
    print("=" * 60)
    print("  (No facts injected into system prompt — retrieval on demand)\n")

    # Re-instantiate the store to prove it loaded from disk
    global _store
    _store = HybridMemoryStore()
    print(f"  [HybridStore] Reloaded {len(_store)} entries from disk.\n")

    agent2 = make_agent(
        "Session-2",
        system_note=f"There are {len(_store)} facts in long-term memory. Use recall() to fetch relevant ones before answering.",
    )
    agent2.run("What do you know about Alice? What model does she prefer?")

    print("\n" + "=" * 60)
    print("SESSION 3: Keyword vs semantic — BM25 catches exact terms")
    print("=" * 60)

    agent3 = make_agent(
        "Session-3",
        system_note=f"There are {len(_store)} facts in long-term memory. Use recall() to fetch relevant ones before answering.",
    )
    agent3.run("What infrastructure does the team use for deployments and database?")


if __name__ == "__main__":
    main()
