from common import single_run_page

single_run_page(
    "Orchestrator / Worker",
    "The orchestrator decomposes the goal and spawns specialist workers via a delegate_to_agent tool; "
    "worker results come back as ordinary observations.",
    "examples/03_multi_agent_systems/01_orchestrator_worker.py",
    builder="build_orchestrator",
    default_prompt_attr="DEFAULT_GOAL",
)
