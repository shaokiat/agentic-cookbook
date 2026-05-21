from pathlib import Path

# Loaded from prompts/system.md so prompt edits don't require touching Python files.
SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "system.md").read_text()
