import os
from typing import Any

import requests

SCHEMA = {
    "name": "search_web",
    "description": (
        "Search the web for recent information. Use for current news, recent events, "
        "analyst commentary, or any topic where yfinance data may be stale or absent. "
        "Returns titles, URLs, and snippets from search results."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query, e.g. 'AAPL earnings Q2 2026' or 'Apple Vision Pro demand'",
            },
            "count": {
                "type": "integer",
                "description": "Number of results to return (1-10, default 5)",
            },
        },
        "required": ["query"],
    },
}


def search_web(query: str, count: int = 5) -> list[dict[str, Any]]:
    """Search the web using the Brave Search API."""
    api_key = os.environ.get("BRAVE_API_KEY")
    if not api_key:
        return [{"error": "BRAVE_API_KEY not set — web search unavailable"}]

    try:
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
            params={"q": query, "count": min(count, 10)},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("web", {}).get("results", [])[:count]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
                "published": item.get("page_age", ""),
            })
        return results if results else [{"message": "No results found"}]
    except Exception as e:
        return [{"error": str(e)}]
