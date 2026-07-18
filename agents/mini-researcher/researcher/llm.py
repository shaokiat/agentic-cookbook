from typing import List, Dict

import litellm
from pydantic import BaseModel

litellm.success_callback = []


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0


class LLM:
    """Thin litellm wrapper with cumulative cost tracking, adapted from core/model.py."""

    def __init__(self, model: str):
        self.model = model
        self.cumulative_usage = Usage()

    def complete(self, messages: List[Dict[str, str]]) -> str:
        response = litellm.completion(model=self.model, messages=messages)
        content = response.choices[0].message.content

        usage_data = response.usage
        cost = litellm.completion_cost(completion_response=response)
        self.cumulative_usage.prompt_tokens += usage_data.prompt_tokens
        self.cumulative_usage.completion_tokens += usage_data.completion_tokens
        self.cumulative_usage.total_tokens += usage_data.total_tokens
        self.cumulative_usage.cost += cost

        return content

    def embed_batch(self, texts: List[str], embedding_model: str) -> List[List[float]]:
        response = litellm.embedding(model=embedding_model, input=texts)
        cost = litellm.completion_cost(completion_response=response) or 0.0
        self.cumulative_usage.cost += cost
        return [item["embedding"] for item in response.data]
