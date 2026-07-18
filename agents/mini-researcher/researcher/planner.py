import json
import re

from researcher.llm import LLM
from researcher.prompts import load


def generate_sub_queries(llm: LLM, query: str, max_sub_queries: int) -> list[str]:
    """Query -> list of sub-questions, via one LLM call with a defensive parse fallback chain."""
    system_prompt = load("planner.md", max_sub_queries=max_sub_queries)
    raw = llm.complete([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ])
    return _parse_sub_queries(raw, fallback_query=query)


def _parse_sub_queries(raw: str, fallback_query: str) -> list[str]:
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list) and all(isinstance(q, str) for q in parsed) and parsed:
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list) and all(isinstance(q, str) for q in parsed) and parsed:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

    return [fallback_query]
