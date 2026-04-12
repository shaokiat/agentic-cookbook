# 04 Tool Use Patterns

Advanced patterns for how agents interact with the physical and digital world.

## Core Concepts to Explore
1. **Dynamic Tool Loading**: Discovering and loading tool definitions at runtime (e.g., from a plugin directory).
2. **Context-Aware Tools**: Tools that use the `context` parameter to access the agent's internal state or memory.
3. **Human-in-the-Loop (HIL)**: Requiring human approval for high-risk tool calls (e.g., executing shell commands, making payments).
4. **Tool Outputs as Data**: Handling non-text tool outputs (files, images, structured JSON).

## Suggested Next Example
- `01_human_approval.py`: A tool that requires the user to type 'yes' in the console before a command is executed.
