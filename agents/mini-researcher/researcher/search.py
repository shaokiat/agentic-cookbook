from typing import Protocol, TypedDict


class SearchResult(TypedDict):
    title: str
    url: str
    snippet: str


class SearchProvider(Protocol):
    def search(self, query: str, n: int = 5) -> list[SearchResult]: ...


class DuckDuckGoProvider:
    def search(self, query: str, n: int = 5) -> list[SearchResult]:
        from ddgs import DDGS

        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=n)
        return [
            {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
            for r in results
        ]


def get_search_provider(name: str) -> SearchProvider:
    if name == "duckduckgo":
        return DuckDuckGoProvider()
    raise ValueError(f"Unknown search provider: {name}")
