"""Read deploy/engines.yaml for the Makefile, serve.sh, and the harness.

YAML is the source of truth; Make and bash cannot parse it, so this renders the same
values into the two flat forms they can consume. Keys become <SECTION>_<KEY> — vllm.model
is VLLM_MODEL — except `local`, which drops the prefix (LOCAL_PORT, LOCAL_API_KEY).

    python deploy/engines.py --make          # KEY=VALUE, for `include`
    python deploy/engines.py --sh            # : "${KEY:=value}", for `eval` in bash
    python deploy/engines.py get vllm.model  # one value
"""
import sys
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parent / "engines.yaml"


def load(path: Path = CONFIG) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def flatten(config: dict) -> dict[str, str]:
    """{'vllm': {'model': 'x'}} -> {'VLLM_MODEL': 'x'}. Booleans become 1/0 for shell."""
    out = {}
    for section, values in config.items():
        if not isinstance(values, dict):
            continue
        prefix = "" if section == "local" else f"{section.upper()}_"
        for key, value in values.items():
            if isinstance(value, bool):
                value = int(value)
            out[f"{prefix}{key.upper()}" if prefix else f"LOCAL_{key.upper()}"] = str(value)
    return out


def main(argv: list[str]) -> int:
    if not CONFIG.exists():
        print(f"missing {CONFIG}", file=sys.stderr)
        return 1
    flat = flatten(load())

    if argv and argv[0] == "get":
        print(flat.get(argv[1].replace(".", "_").upper(), ""))
    elif argv and argv[0] == "--sh":
        # Assign only if unset, so an environment override still wins.
        for key, value in flat.items():
            print(f': "${{{key}:={value}}}"')
    else:
        for key, value in flat.items():
            print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
