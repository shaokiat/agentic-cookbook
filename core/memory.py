from typing import List, Dict, Any, Optional
import json

class Memory:
    def __init__(self, initial_messages: Optional[List[Dict[str, str]]] = None):
        self.messages = initial_messages or []

    def add_message(self, role: str, content: str, tool_calls: Optional[List[Dict[str, Any]]] = None, tool_call_id: Optional[str] = None, name: Optional[str] = None):
        """
        Add a message to the history.
        """
        message = {"role": role, "content": content}
        
        if tool_calls:
            message["tool_calls"] = tool_calls
        if tool_call_id:
            message["tool_call_id"] = tool_call_id
        if name:
            message["name"] = name
            
        self.messages.append(message)

    def get_messages(self) -> List[Dict[str, Any]]:
        return self.messages

    def clear(self):
        self.messages = []

    def save_to_file(self, file_path: str):
        with open(file_path, "w") as f:
            json.dump(self.messages, f, indent=2)

    @classmethod
    def load_from_file(cls, file_path: str) -> 'Memory':
        with open(file_path, "r") as f:
            messages = json.load(f)
        return cls(messages)
