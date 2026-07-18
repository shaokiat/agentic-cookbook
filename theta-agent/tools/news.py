from typing import Any
import yfinance as yf

from theta.models import NewsItem

SCHEMA = {
    "name": "get_news",
    "description": (
        "Fetch recent news headlines and summaries for a ticker symbol. "
        "Returns up to 10 recent articles with title, publisher, and summary."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol, e.g. AAPL, TSLA, SPY",
            }
        },
        "required": ["ticker"],
    },
}


def get_news(ticker: str) -> list[dict[str, Any]]:
    """Fetch recent news headlines and summaries for a ticker symbol."""
    try:
        stock = yf.Ticker(ticker)
        raw_news = stock.news or []

        items: list[NewsItem] = []
        for item in raw_news[:10]:
            content = item.get("content", {})
            if content:
                items.append(NewsItem(
                    title=content.get("title", ""),
                    publisher=content.get("provider", {}).get("displayName", ""),
                    summary=content.get("summary", ""),
                    published=content.get("pubDate", ""),
                ))
            else:
                items.append(NewsItem(
                    title=item.get("title", ""),
                    publisher=item.get("publisher", ""),
                    summary=item.get("summary", ""),
                    published=str(item.get("providerPublishTime", "")),
                ))

        if not items:
            return [NewsItem(message="No recent news found").model_dump(exclude_none=True)]
        return [i.model_dump(exclude_none=True) for i in items]
    except Exception as e:
        return [NewsItem(error=str(e)).model_dump(exclude_none=True)]
