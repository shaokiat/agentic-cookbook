import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from researcher.config import Config
from researcher.llm import LLM
from researcher.planner import generate_sub_queries
from researcher.prompts import load
from researcher.report import Report
from researcher.search import get_search_provider
from researcher.worker import _emit, run_subquery_worker


class ResearchPipeline:
    def __init__(self, config: Config | None = None, on_event=None):
        self.config = config or Config()
        self.llm = LLM(self.config.model)
        self.search_provider = get_search_provider(self.config.search_provider)
        self.on_event = on_event

    def run(self, query: str) -> Report:
        sub_queries = generate_sub_queries(self.llm, query, self.config.max_sub_queries)
        _emit(self.on_event, "planning_done", sub_queries=sub_queries)

        start = time.perf_counter()
        contexts = self._fan_out(sub_queries)
        timing = {"research_seconds": time.perf_counter() - start}

        context = "\n\n".join(c for c in contexts if c)
        _emit(self.on_event, "synthesizing")
        content = self._synthesize(query, context)
        _emit(self.on_event, "done")

        return Report(
            query=query,
            sub_queries=sub_queries,
            content=content,
            usage=self.llm.cumulative_usage,
            timing=timing,
        )

    def _fan_out(self, sub_queries: list[str]) -> list[str]:
        results: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=len(sub_queries)) as executor:
            futures = {
                executor.submit(run_subquery_worker, sq, self.search_provider, self.llm, self.config, self.on_event): i
                for i, sq in enumerate(sub_queries)
            }
            for future in as_completed(futures):
                i = futures[future]
                try:
                    results[i] = future.result()
                except Exception:
                    results[i] = ""
        return [results[i] for i in range(len(sub_queries))]

    def _synthesize(self, query: str, context: str) -> str:
        system_prompt = load("synthesis.md")
        user_prompt = (
            f"Query: {query}\n\nContext:\n{context}" if context
            else f"Query: {query}\n\nContext: (no relevant sources were found)"
        )
        return self.llm.complete([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
