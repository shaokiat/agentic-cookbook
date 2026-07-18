from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load(name: str, **kwargs) -> str:
    text = (PROMPTS_DIR / name).read_text()
    return text.format(**kwargs) if kwargs else text
