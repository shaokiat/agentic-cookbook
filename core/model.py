import os
from typing import List, Dict, Any, Optional
import litellm
from pydantic import BaseModel, Field

# Enable usage tracking
litellm.success_callback = []

class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0

class ModelResponse(BaseModel):
    content: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    raw_response: Any = None

class ModelProvider:
    def __init__(self, model: Optional[str] = None):
        self.model = model or os.getenv("DEFAULT_MODEL", "openai/gpt-4o")
        self.cumulative_usage = Usage()

    def generate(
        self, 
        messages: List[Dict[str, str]], 
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto"
    ) -> ModelResponse:
        """
        Generate a response from the model.
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
        }
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        response = litellm.completion(**kwargs)
        
        content = response.choices[0].message.content
        tool_calls = getattr(response.choices[0].message, "tool_calls", []) or []
        
        # Convert tool calls to dicts
        formatted_tool_calls = []
        for tc in tool_calls:
            formatted_tool_calls.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments
                }
            })

        # Track usage
        usage_data = response.usage
        cost = litellm.completion_cost(completion_response=response)
        
        current_usage = Usage(
            prompt_tokens=usage_data.prompt_tokens,
            completion_tokens=usage_data.completion_tokens,
            total_tokens=usage_data.total_tokens,
            cost=cost
        )
        
        self.cumulative_usage.prompt_tokens += current_usage.prompt_tokens
        self.cumulative_usage.completion_tokens += current_usage.completion_tokens
        self.cumulative_usage.total_tokens += current_usage.total_tokens
        self.cumulative_usage.cost += current_usage.cost

        return ModelResponse(
            content=content,
            tool_calls=formatted_tool_calls,
            usage=current_usage,
            raw_response=response
        )

    def get_cumulative_usage(self) -> Usage:
        return self.cumulative_usage
