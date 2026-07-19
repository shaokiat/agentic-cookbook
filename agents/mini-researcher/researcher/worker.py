from researcher.compress import chunk_text, filter_relevant_chunks
from researcher.config import Config
from researcher.llm import LLM
from researcher.scraper import scrape
from researcher.search import SearchProvider

CONTEXT_BLOCK = "Source: {url}\n{text}"


def _emit(on_event, stage: str, **kw) -> None:
    if on_event is None:
        return
    try:
        on_event({"stage": stage, **kw})
    except Exception:
        pass


def run_subquery_worker(sub_query: str, search_provider: SearchProvider, llm: LLM, config: Config, on_event=None) -> str:
    """search -> scrape -> chunk -> compress for one sub-query.

    Isolated by design: any failure at any stage yields an empty string
    rather than propagating, so one bad sub-query never kills the run.
    """
    _emit(on_event, "subquery_start", sub_query=sub_query)
    try:
        results = search_provider.search(sub_query, n=config.results_per_query)
    except Exception:
        _emit(on_event, "subquery_done", sub_query=sub_query, blocks=0)
        return ""
    _emit(on_event, "searched", sub_query=sub_query, n_results=len(results))

    blocks = []
    for result in results:
        doc = scrape(result["url"])
        if doc is None:
            continue
        _emit(on_event, "scraped", sub_query=sub_query, url=doc.url)

        chunks = chunk_text(doc.text, config.chunk_size, config.chunk_overlap)
        try:
            relevant = filter_relevant_chunks(llm, config.embedding_model, sub_query, chunks, config.top_k_chunks)
        except Exception:
            relevant = chunks[:config.top_k_chunks]

        for chunk in relevant:
            blocks.append(CONTEXT_BLOCK.format(url=doc.url, text=chunk))

    _emit(on_event, "subquery_done", sub_query=sub_query, blocks=len(blocks))
    return "\n\n".join(blocks)
