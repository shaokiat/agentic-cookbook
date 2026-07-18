#!/usr/bin/env python3
"""Pretty-print a theta-agent JSONL session log.

Usage:
    python read_log.py [path/to/session.jsonl]

If no path is given, the most recent log in logs/ is used.
"""
import json
import sys
from pathlib import Path
from datetime import datetime


def ts(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%H:%M:%S")


def fmt_price(result: dict) -> str:
    lines = [
        f"  price    ${result.get('current_price', '?')}  |  prev close ${result.get('previous_close', '?')}",
        f"  52w      ${result.get('low_52w', '?')} – ${result.get('high_52w', '?')}",
        f"  P/E      {result.get('pe_ratio', 'n/a')}  |  beta {result.get('beta', 'n/a')}",
        f"  1mo ret  {result.get('return_1mo_pct', 'n/a')}%",
        f"  sector   {result.get('sector', 'n/a')} / {result.get('industry', 'n/a')}",
    ]
    return "\n".join(lines)


def fmt_news(items: list) -> str:
    lines = []
    for i, item in enumerate(items[:5], 1):
        pub = item.get("publisher", "")
        title = item.get("title", "")
        lines.append(f"  {i}. [{pub}] {title}")
    if len(items) > 5:
        lines.append(f"  … and {len(items) - 5} more")
    return "\n".join(lines)


def fmt_options(result: dict) -> str:
    lines = [
        f"  expiry      {result.get('expiry')}",
        f"  spot        ${result.get('current_price')}  |  ATM IV {result.get('atm_iv', 'n/a')}",
    ]
    calls = result.get("calls", [])
    puts = result.get("puts", [])
    if calls:
        lines.append("  calls (top by OI):")
        for c in calls:
            lines.append(
                f"    ${c['strike']:>7}  bid {c.get('bid','?'):>5}  ask {c.get('ask','?'):>5}"
                f"  IV {c.get('iv','?'):>6}  OI {c.get('open_interest','?'):>6}"
            )
    if puts:
        lines.append("  puts (top by OI):")
        for p in puts:
            lines.append(
                f"    ${p['strike']:>7}  bid {p.get('bid','?'):>5}  ask {p.get('ask','?'):>5}"
                f"  IV {p.get('iv','?'):>6}  OI {p.get('open_interest','?'):>6}"
            )
    return "\n".join(lines)


TOOL_FORMATTERS = {
    "get_price_data": fmt_price,
    "get_news": fmt_news,
    "get_options_chain": fmt_options,
}


def render(path: Path) -> None:
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    for rec in records:
        event = rec["event"]
        t = ts(rec["ts"])

        if event == "session_start":
            print(f"\n{'='*60}")
            print(f"  SESSION  {rec['ticker']}  started {t}")
            print(f"{'='*60}")

        elif event == "tool_call":
            name = rec["tool"]
            result_raw = rec.get("result", "{}")
            try:
                result = json.loads(result_raw)
            except (json.JSONDecodeError, TypeError):
                result = result_raw

            print(f"\n[{t}] TOOL  {name}({rec['input'].get('ticker', '')})")
            if "error" in (result if isinstance(result, dict) else {}):
                print(f"  ERROR: {result['error']}")
            else:
                formatter = TOOL_FORMATTERS.get(name)
                if formatter:
                    print(formatter(result))
                else:
                    print(f"  {json.dumps(result, indent=2)[:300]}")

        elif event == "api_response":
            stop = rec.get("stop_reason")
            if stop == "tool_use":
                names = [b["name"] for b in rec.get("content", []) if b.get("type") == "tool_use"]
                print(f"\n[{t}] CLAUDE → requesting tools: {', '.join(names)}")
            elif stop == "end_turn":
                for block in rec.get("content", []):
                    if block.get("type") == "text":
                        print(f"\n[{t}] CLAUDE SUMMARY\n{'-'*60}")
                        print(block["text"])
                        print(f"{'-'*60}")

        elif event == "session_end":
            print(f"\n[{t}] SESSION END\n")


def main() -> None:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        logs_dir = Path(__file__).parent / "logs"
        logs = sorted(logs_dir.glob("*.jsonl"))
        if not logs:
            sys.exit("No logs found in logs/")
        path = logs[-1]

    print(f"Log: {path.name}")
    render(path)


if __name__ == "__main__":
    main()
