# Thin shim — implementations live in tools/ (one file per tool).
# Importing TOOLS and process_tool_call from here gives the same mutable list
# and dispatcher as importing from `tools` directly, so theta/agent.py is unchanged.
from tools import TOOLS, process_tool_call  # noqa: F401
