import json
import os
from typing import Any

from .price import get_price_data, SCHEMA as PRICE_SCHEMA
from .news import get_news, SCHEMA as NEWS_SCHEMA
from .options import get_options_chain, SCHEMA as OPTIONS_SCHEMA
from .financials import get_financials, SCHEMA as FINANCIALS_SCHEMA
from .search import search_web, SCHEMA as SEARCH_SCHEMA
from .earnings import get_earnings_dates, SCHEMA as EARNINGS_SCHEMA

TOOLS: list[dict] = [
    PRICE_SCHEMA,
    NEWS_SCHEMA,
    FINANCIALS_SCHEMA,
    OPTIONS_SCHEMA,
    EARNINGS_SCHEMA,
]

_DISPATCH: dict[str, Any] = {
    "get_price_data": get_price_data,
    "get_news": get_news,
    "get_financials": get_financials,
    "get_options_chain": get_options_chain,
    "get_earnings_dates": get_earnings_dates,
}

if os.environ.get("BRAVE_API_KEY"):
    TOOLS.append(SEARCH_SCHEMA)
    _DISPATCH["search_web"] = search_web


def process_tool_call(tool_name: str, tool_input: dict[str, Any]) -> str:
    fn = _DISPATCH.get(tool_name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    return json.dumps(fn(**tool_input), indent=2, default=str)
