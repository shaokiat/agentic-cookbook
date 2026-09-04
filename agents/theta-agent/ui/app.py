"""Chainlit front-end for the screener. Presentation only — no state transformation here."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chainlit as cl
import pandas as pd
from langgraph.types import Command

from config.themes import WATCHLIST
from graph.build import compiled_graph

LEAPS_COLS = ["ticker", "strike", "expiry", "dte", "delta", "mid", "breakeven",
              "iv_rank", "open_interest", "theme"]
CSP_COLS = ["ticker", "strike", "expiry", "dte", "delta", "mid", "collateral_required",
            "collateral_flag", "iv_rank", "open_interest", "theme"]


def candidate_frame(rows: list[dict], strategy: str) -> pd.DataFrame:
    """Strategy-appropriate columns. Pure — cl.Dataframe needs a live session, this doesn't."""
    cols = LEAPS_COLS if strategy == "long_leaps" else CSP_COLS
    df = pd.DataFrame(rows)
    # Reindex defensively: an optional field absent from every row would KeyError.
    return df[[c for c in cols if c in df.columns]]


def _table(rows: list[dict], strategy: str) -> cl.Dataframe:
    return cl.Dataframe(data=candidate_frame(rows, strategy), display="inline", name="candidates")


async def _report_errors(errors: list[dict]) -> None:
    if not errors:
        return
    lines = "\n".join(f"- **{e['ticker']}** ({e['node']}): {e['message']}" for e in errors)
    await cl.Message(content=f"⚠️ {len(errors)} ticker(s) could not be screened:\n{lines}").send()


@cl.on_chat_start
async def start():
    res = await cl.AskActionMessage(
        content="Strategy:",
        actions=[
            cl.Action(name="long_leaps", payload={"value": "long_leaps"}, label="Long ITM LEAPS"),
            cl.Action(name="csp", payload={"value": "csp"}, label="Cash-Secured Put"),
        ],
    ).send()
    if not res:
        return
    strategy = res["payload"]["value"]

    tickers = None
    while not tickers:
        reply = await cl.AskUserMessage(
            content=f"Tickers to screen, comma-separated (or `all`).\n\n`{', '.join(WATCHLIST)}`",
            timeout=180,
        ).send()
        if not reply:
            return
        raw = reply["output"].strip()
        if raw.lower() == "all":
            tickers = list(WATCHLIST)
            break
        requested = [t.strip().upper() for t in raw.split(",") if t.strip()]
        unknown = [t for t in requested if t not in WATCHLIST]
        if unknown or not requested:
            await cl.Message(content=f"Not in the watchlist: `{', '.join(unknown) or '(none given)'}`. Try again.").send()
            continue
        tickers = requested

    config = {"configurable": {"thread_id": cl.context.session.id}}
    cl.user_session.set("config", config)
    cl.user_session.set("strategy", strategy)
    await run_graph({"selected_tickers": tickers, "strategy_type": strategy}, config)


async def run_graph(payload, config):
    strategy = cl.user_session.get("strategy")
    async with cl.Step(name="screening", type="run") as step:
        step.output = f"{len(payload['selected_tickers'])} tickers" if isinstance(payload, dict) else "resuming"
        async for event in compiled_graph.astream(payload, config=config):
            if "__interrupt__" in event:
                await present_for_review(event["__interrupt__"][0].value, strategy)
                return
            for node in event:
                await cl.Message(content=f"✓ {node}").send()

    state = compiled_graph.get_state(config).values
    await _report_errors(state.get("errors", []))
    final = state.get("final_candidates", [])
    if not final:
        await cl.Message(content="No candidates. Run rejected, or nothing passed screening.").send()
        return
    await cl.Message(content=f"**{len(final)} candidates**", elements=[_table(final, strategy)]).send()


async def present_for_review(interrupt_value: dict, strategy: str):
    candidates = interrupt_value["candidates"]
    await _report_errors(interrupt_value.get("errors", []))

    if not candidates:
        await cl.Message(content="No candidates passed screening. Nothing to approve.").send()
    else:
        await cl.Message(content=f"**{len(candidates)} candidates for review**",
                         elements=[_table(candidates, strategy)]).send()

    res = await cl.AskActionMessage(
        content="Approve these candidates?",
        actions=[
            cl.Action(name="approve", payload={"value": "approve"}, label="Approve"),
            cl.Action(name="reject", payload={"value": "reject"}, label="Reject"),
            cl.Action(name="resubmit", payload={"value": "resubmit"}, label="Re-screen"),
        ],
        timeout=600,
    ).send()
    action = res["payload"]["value"] if res else "reject"

    if action == "resubmit":
        await cl.Message(content="Re-screening with adjusted parameters is not implemented yet — "
                                 "start a new chat to change the selection. Treating this as a reject.").send()
        action = "reject"

    await run_graph(Command(resume={"action": action}), cl.user_session.get("config"))
