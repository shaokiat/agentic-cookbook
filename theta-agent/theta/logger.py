import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SessionLogger:
    """Write structured JSONL logs for a single research session."""

    def __init__(self, ticker: str, log_dir: Path | None = None):
        base = log_dir or Path(__file__).parent.parent / "logs"
        base.mkdir(exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = base / f"{ts}_{ticker}.jsonl"
        self._f = self.path.open("w", buffering=1)
        self._write("session_start", {"ticker": ticker})

    def _write(self, event: str, extra: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **extra,
        }
        self._f.write(json.dumps(record, default=str) + "\n")

    def api_request(self, messages: list) -> None:
        self._write("api_request", {"messages": messages})

    def api_response(self, stop_reason: str, content: list) -> None:
        blocks = []
        for b in content:
            block: dict[str, Any] = {"type": getattr(b, "type", "text")}
            if hasattr(b, "text"):
                block["text"] = b.text
            if getattr(b, "type", None) == "tool_use":
                block.update({"name": b.name, "input": b.input, "id": b.id})
            blocks.append(block)
        self._write("api_response", {"stop_reason": stop_reason, "content": blocks})

    def tool_call(self, name: str, input_: dict, result: str) -> None:
        self._write("tool_call", {"tool": name, "input": input_, "result": result})

    def session_end(self) -> None:
        self._write("session_end", {})
        self._f.close()
