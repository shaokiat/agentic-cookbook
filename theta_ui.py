#!/usr/bin/env python3
"""theta-agent TUI: single-pane Textual terminal interface."""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

import re

import anthropic
from rich.rule import Rule
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Button, Footer, Header, Input, Label, RichLog, Static

from theta.agent import ThetaAgent
from theta import state as state_store

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

_TOOL_ICONS: dict[str, str] = {
    "get_price_data":    "📈",
    "get_news":          "📰",
    "get_options_chain": "⚙️ ",
    "get_financials":    "💰",
    "get_earnings_dates":"📅",
    "search_web":        "🔍",
}


# ── Position modal ────────────────────────────────────────────────────────────

class PositionScreen(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "skip", "Skip")]

    def __init__(self, ticker: str, stored: str | None) -> None:
        super().__init__()
        self.ticker = ticker
        self.stored = stored

    def compose(self) -> ComposeResult:
        with Vertical(id="position-dialog"):
            yield Label(f"💼  [bold]Position for {self.ticker}[/bold]", id="dialog-title")
            if self.stored:
                yield Label(f"  {self.stored}", id="stored-position")
                yield Label(
                    "[dim]Enter new position to update, blank to keep, or 'clear' to remove[/dim]"
                )
            else:
                yield Label("[dim]Optional — press Enter or Skip to skip[/dim]")
            yield Input(placeholder="e.g. Long 100 shares @ $178", id="position-input")
            with Horizontal(id="position-buttons"):
                yield Button("Confirm", variant="primary", id="confirm")
                yield Button("Skip", id="skip")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "skip":
            self.dismiss(self.stored)
        else:
            self._submit(self.query_one("#position-input", Input).value.strip())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit(event.value.strip())

    def action_skip(self) -> None:
        self.dismiss(self.stored)

    def _submit(self, value: str) -> None:
        if value.lower() == "clear":
            self.dismiss(None)
        elif value:
            self.dismiss(value)
        else:
            self.dismiss(self.stored)


# ── Main app ──────────────────────────────────────────────────────────────────

class ThetaApp(App):
    CSS = """
    Screen { background: $surface; }

    #log {
        height: 1fr;
        padding: 0 1;
        scrollbar-gutter: stable;
    }

    #activity {
        height: 1;
        padding: 0 1;
        background: $boost;
        color: $text-muted;
    }

    #input-row {
        height: 3;
        padding: 0 1;
        border-top: tall $primary-darken-2;
    }

    #chat-input { width: 1fr; }

    #send-btn {
        width: 10;
        margin-left: 1;
    }

    /* Position modal */
    PositionScreen { align: center middle; }

    #position-dialog {
        background: $surface;
        border: double $primary;
        padding: 1 2;
        width: 72;
        height: auto;
    }

    #dialog-title {
        color: $accent;
        margin-bottom: 1;
    }

    #stored-position {
        color: $warning;
        margin-bottom: 1;
    }

    #position-buttons {
        margin-top: 1;
        height: 3;
    }

    #position-buttons Button { margin-right: 1; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+q", "quit", "Quit", show=False),
    ]

    # Spinner state — only touched on the main thread
    _spin_timer: Timer | None = None
    _spin_idx: int = 0
    _spin_msg: str = ""

    def __init__(self, ticker: str) -> None:
        super().__init__()
        self.ticker = ticker.upper()
        self.agent: ThetaAgent | None = None
        self.chat_messages: list = []
        self._research_done = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RichLog(id="log", markup=True, wrap=True, highlight=False)
        yield Static("", id="activity")
        with Horizontal(id="input-row"):
            yield Input(
                placeholder="Ask a follow-up — /summary /scorecard /strategy /position /exit",
                id="chat-input",
                disabled=True,
            )
            yield Button("Send ↵", id="send-btn", variant="primary", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"theta-agent  |  {self.ticker}"
        self._start()

    # ── Spinner (main-thread only) ────────────────────────────────────────────

    def _start_spinner(self, msg: str) -> None:
        self._spin_msg = msg
        self._spin_idx = 0
        if self._spin_timer is None:
            self._spin_timer = self.set_interval(0.08, self._tick_spinner)

    def _stop_spinner(self, msg: str = "", ok: bool = True) -> None:
        if self._spin_timer is not None:
            self._spin_timer.stop()
            self._spin_timer = None
        if msg:
            icon = "✅" if ok else "❌"
            color = "green" if ok else "red"
            self.query_one("#activity", Static).update(
                f"[bold {color}]{icon}  {msg}[/]"
            )

    def _tick_spinner(self) -> None:
        frame = _SPINNER_FRAMES[self._spin_idx % len(_SPINNER_FRAMES)]
        self._spin_idx += 1
        self.query_one("#activity", Static).update(
            f"[bold yellow]{frame}[/]  [yellow]{self._spin_msg}[/]"
        )

    def _update_spin_msg(self, msg: str) -> None:
        self._spin_msg = msg

    # ── Startup ───────────────────────────────────────────────────────────────

    def _start(self) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            self._log("[bold red]❌  ANTHROPIC_API_KEY not set.[/]")
            return

        stored_state = state_store.load(self.ticker)
        prior_ctx = state_store.prior_context(stored_state)
        stored_position = stored_state.get("position")

        if prior_ctx:
            n = len(stored_state.get("sessions", []))
            self._log(f"[dim]📂  {n} previous session(s) found for {self.ticker}[/]")

        self._prior_ctx = prior_ctx
        self._api_key = api_key

        self.push_screen(
            PositionScreen(self.ticker, stored_position),
            callback=self._on_position_confirmed,
        )

    def _on_position_confirmed(self, position: str | None) -> None:
        self._position = position
        if position:
            self._log(f"[dim]💼  Position: {position}[/]")

        client = anthropic.Anthropic(api_key=self._api_key)
        self.agent = ThetaAgent(
            ticker=self.ticker,
            client=client,
            positions=position,
            prior_context=self._prior_ctx,
            on_output=lambda text: self.call_from_thread(self._log, text),
            on_tool_call=self._cb_tool_call,
            on_status=lambda text: self.call_from_thread(self._update_spin_msg, text),
        )

        self._log("")
        self._log(f"[bold cyan]🔬  Researching {self.ticker}...[/]")
        self._start_spinner(f"Researching {self.ticker}...")
        self._run_research()

    # ── Research worker ───────────────────────────────────────────────────────

    @work(thread=True)
    def _run_research(self) -> None:
        assert self.agent is not None
        try:
            summary, messages = self.agent.run_research()
        except Exception as exc:
            self.call_from_thread(self._research_error, str(exc))
            return
        self.chat_messages = list(messages)
        self.call_from_thread(self._on_research_complete, summary)

    def _research_error(self, msg: str) -> None:
        self._stop_spinner(f"Research failed: {msg}", ok=False)
        self._log(f"[bold red]❌  {msg}[/]")

    def _on_research_complete(self, summary: str) -> None:
        self._stop_spinner(f"{self.ticker} research complete", ok=True)

        self._log("")
        self._log(Rule(style="dim"))
        self._log(summary)
        self._log(Rule("[dim]chat[/dim]", style="dim"))
        self._log("")

        chat_input = self.query_one("#chat-input", Input)
        send_btn = self.query_one("#send-btn", Button)
        chat_input.disabled = False
        send_btn.disabled = False
        chat_input.focus()
        self._research_done = True

    # ── Chat ──────────────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            self._submit_chat()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "chat-input":
            self._submit_chat()

    def _submit_chat(self) -> None:
        if not self._research_done:
            return
        chat_input = self.query_one("#chat-input", Input)
        text = chat_input.value.strip()
        if not text:
            return
        chat_input.value = ""

        if text.lower() in ("exit", "quit", "q", "/exit"):
            self._save_and_quit()
            return

        self._log(f"[bold cyan]💬  You:[/]  {text}")
        chat_input.disabled = True
        self.query_one("#send-btn", Button).disabled = True
        self._start_spinner("Thinking...")
        self._send_chat(text)

    @work(thread=True)
    def _send_chat(self, text: str) -> None:
        assert self.agent is not None
        try:
            reply = self.agent.send_message(text, self.chat_messages)
        except Exception as exc:
            reply = f"[bold red]Error:[/] {exc}"
        self.call_from_thread(self._on_chat_reply, reply)

    def _on_chat_reply(self, reply: str) -> None:
        self._stop_spinner()
        self._log(f"[bold green]🤖  Claude:[/]  {reply}")
        self._log("")
        chat_input = self.query_one("#chat-input", Input)
        send_btn = self.query_one("#send-btn", Button)
        chat_input.disabled = False
        send_btn.disabled = False
        chat_input.focus()
        self.query_one("#activity", Static).update("[dim]Ready[/]")

    # ── Agent callbacks (called from worker thread) ───────────────────────────

    def _cb_tool_call(self, name: str, preview: str) -> None:
        icon = _TOOL_ICONS.get(name, "🔧")
        self.call_from_thread(
            self._log, f"[dim]  {icon}  {name}({preview})[/]"
        )
        self.call_from_thread(
            self._update_spin_msg, f"{icon}  {name}({preview})"
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, text: object) -> None:
        self.query_one("#log", RichLog).write(text)

    # ── Quit / save ───────────────────────────────────────────────────────────

    def _save_and_quit(self) -> None:
        if self.agent and self.chat_messages:
            self._stop_spinner()
            self._log("[dim]💾  Saving session...[/]")
            self.query_one("#activity", Static).update("[dim]💾  Saving...[/]")
            self.agent._save_session(self.chat_messages)
        self.exit()

    def action_quit(self) -> None:
        self._save_and_quit()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python theta_ui.py <TICKER>")
        print("Example: python theta_ui.py AAPL")
        sys.exit(1)

    ThetaApp(sys.argv[1]).run()


if __name__ == "__main__":
    main()
