from researcher.compress import chunk_text, filter_relevant_chunks
from researcher.config import Config
from researcher.llm import LLM
from researcher.scraper import scrape
from researcher.search import SearchProvider

CONTEXT_BLOCK = "Source: {url}\n{text}"


def run_subquery_worker(sub_query: str, search_provider: SearchProvider, llm: LLM, config: Config) -> str:
    """search -> scrape -> chunk -> compress for one sub-query.

    Isolated by design: any failure at any stage yields an empty string
    rather than propagating, so one bad sub-query never kills the run.
    """
    try:
        results = search_provider.search(sub_query, n=config.results_per_query)
    except Exception:
        return ""

    blocks = []
    for result in results:
        doc = scrape(result["url"])
        if doc is None:
            continue

        chunks = chunk_text(doc.text, config.chunk_size, config.chunk_overlap)
        try:
            relevant = filter_relevant_chunks(llm, config.embedding_model, sub_query, chunks, config.top_k_chunks)
        except Exception:
            relevant = chunks[:config.top_k_chunks]

        for chunk in relevant:
            blocks.append(CONTEXT_BLOCK.format(url=doc.url, text=chunk))

    return "\n\n".join(blocks)
