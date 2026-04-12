import inspect
import json
from typing import Callable, Dict, Any, List, Optional, Type, get_type_hints
from pydantic import create_model, BaseModel

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.schemas: List[Dict[str, Any]] = []

    def register(self, func: Callable):
        """
        Decorator to register a function as a tool.
        Dynamically generates the JSON schema from type hints and docstrings.
        """
        name = func.__name__
        self.tools[name] = func
        
        # Generate schema
        schema = self._generate_schema(func)
        self.schemas.append(schema)
        
        return func

    def _generate_schema(self, func: Callable) -> Dict[str, Any]:
        """
        Generate OpenAI-compatible JSON schema for a function.
        """
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or "No description provided."
        
        # Split docstring to get description and parameter descriptions
        # Simple implementation: first line is description
        description = doc.split("\n\n")[0] if "\n\n" in doc else doc
        
        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        type_hints = get_type_hints(func)
        
        for param_name, param in sig.parameters.items():
            # Skip 'context' parameter if present, as it's injected by the Agent
            if param_name == "context":
                continue
                
            param_type = type_hints.get(param_name, Any)
            
            # Map Python types to JSON types
            json_type = self._map_type(param_type)
            
            parameters["properties"][param_name] = {
                "type": json_type,
                "description": self._get_param_doc(doc, param_name)
            }
            
            if param.default == inspect.Parameter.empty:
                parameters["required"].append(param_name)
                
        return {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": description,
                "parameters": parameters,
            }
        }

    def _map_type(self, py_type: Type) -> str:
        if py_type == str: return "string"
        if py_type == int: return "integer"
        if py_type == float: return "number"
        if py_type == bool: return "boolean"
        if py_type == list or getattr(py_type, "__origin__", None) == list: return "array"
        if py_type == dict or getattr(py_type, "__origin__", None) == dict: return "object"
        return "string" # Default to string

    def _get_param_doc(self, doc: str, param_name: str) -> str:
        """
        Extract parameter description from docstring (very simple version).
        Expected format: ':param param_name: description' or similar.
        """
        import re
        match = re.search(f":param {param_name}: (.*)", doc)
        if match:
            return match.group(1).strip()
        return f"The {param_name} parameter."

    def get_schemas(self) -> List[Dict[str, Any]]:
        return self.schemas

    def call_tool(self, name: str, arguments: str, context: Optional[Any] = None) -> Any:
        if name not in self.tools:
            raise ValueError(f"Tool {name} not found in registry.")
            
        args = json.loads(arguments)
        func = self.tools[name]
        
        # If 'context' is in the function signature, inject it
        sig = inspect.signature(func)
        if "context" in sig.parameters:
            args["context"] = context
            
        return func(**args)
