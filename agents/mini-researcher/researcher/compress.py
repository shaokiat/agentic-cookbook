import numpy as np
from rank_bm25 import BM25Okapi

from researcher.llm import LLM

BM25_WEIGHT = 0.3
VECTOR_WEIGHT = 0.7


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Paragraph-aware chunking: pack paragraphs up to chunk_size, falling back
    to hard slicing for any single paragraph longer than chunk_size."""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(para) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(para), chunk_size - overlap):
                chunks.append(para[i:i + chunk_size])
            continue

        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            current = para

    if current:
        chunks.append(current)

    return chunks


def filter_relevant_chunks(llm: LLM, embedding_model: str, query: str, chunks: list[str], top_k: int = 5) -> list[str]:
    """BM25 + cosine-similarity hybrid filter, adapted from HybridMemoryStore
    (examples/02_memory_management/02_hybrid_search.py) but stateless: embeddings
    are computed once for this call and discarded, not persisted."""
    if not chunks:
        return []
    if len(chunks) <= top_k:
        return chunks

    corpus = [c.lower().split() for c in chunks]
    bm25 = BM25Okapi(corpus)
    bm25_raw = bm25.get_scores(query.lower().split())
    bm25_max = bm25_raw.max() if bm25_raw.max() > 0 else 1.0
    bm25_scores = bm25_raw / bm25_max

    embeddings = llm.embed_batch(chunks + [query], embedding_model)
    chunk_embs = np.array(embeddings[:-1])
    query_emb = np.array(embeddings[-1])

    norms = np.linalg.norm(chunk_embs, axis=1) * np.linalg.norm(query_emb)
    norms = np.where(norms == 0, 1.0, norms)
    vector_scores = (chunk_embs @ query_emb) / norms

    combined = BM25_WEIGHT * bm25_scores + VECTOR_WEIGHT * vector_scores
    top_indices = np.argsort(combined)[::-1][:top_k]

    return [chunks[i] for i in top_indices]
