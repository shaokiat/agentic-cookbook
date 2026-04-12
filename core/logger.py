import json
import os
from typing import Dict, Any, Optional

class AgentLogger:
    def __init__(self, log_path: Optional[str] = None):
        self.log_path = log_path
        self.is_markdown = log_path.endswith(".md") if log_path else False

    def log_event(self, data: Dict[str, Any]):
        """
        Record an agent event to the log file.
        Handles formatting and directory creation.
        """
        if not self.log_path:
            return

        # Ensure directory exists
        log_dir = os.path.dirname(self.log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        mode = "w" if data.get("event") == "run_start" else "a"
        
        with open(self.log_path, mode) as f:
            if self.is_markdown:
                self._log_markdown(f, data)
            else:
                self._log_json(f, data)

    def _log_markdown(self, f, data: Dict[str, Any]):
        event = data.get("event", "event").upper()
        step = f"Phase {data['step']}" if "step" in data else "General"
        
        f.write(f"## {event} - {step}\n\n")
        
        if "user_input" in data:
            f.write(f"**User Input:** {data['user_input']}\n\n")
        
        if "content" in data and data["content"]:
            f.write(f"### Assistant Thought\n{data['content']}\n\n")
        
        if "tool_calls" in data and data["tool_calls"]:
            f.write("### Tool Calls Requested\n")
            for tc in data["tool_calls"]:
                f.write(f"- `{tc['function']['name']}({tc['function']['arguments']})`\n")
            f.write("\n")
        
        if "tool" in data:
            f.write(f"### Tool Execution: `{data['tool']}`\n")
            f.write(f"**Arguments:** `{data['arguments']}`\n\n")
            f.write(f"**Observation:**\n```\n{data['observation']}\n```\n\n")
        
        if "final_answer" in data:
            f.write(f"### Final Answer\n{data['final_answer']}\n\n")
        
        f.write("---\n\n")

    def _log_json(self, f, data: Dict[str, Any]):
        # Pretty-printed JSON with separator for readability
        f.write(json.dumps(data, indent=2) + "\n\n---\n\n")
