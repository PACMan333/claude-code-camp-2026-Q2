"""Tui wraps a Repl instance and replaces its raw print()/input() I/O with a
structured four-zone display powered by Textual.

The Repl continues to own session logic (turn counting, /commands, Agent
dispatch). Tui registers an output callback and a Logger subscriber on the
Repl, and drives everything from Textual's own async event loop.

Layout (top -> bottom):
  ┌──────────────────────────────────────────────┐
  │  conversation viewport (scrollable)           │
  ├──────────────────────────────────────────────┤
  │  ⟳ live progress line (hidden when idle)     │
  ├──────────────────────────────────────────────┤
  │  boukensha> input box                         │
  ├──────────────────────────────────────────────┤
  │  status line (always-on)                      │
  └──────────────────────────────────────────────┘

Ruby's equivalent is built on bubbletea (Elm-architecture TUI runtime) +
lipgloss (styling) + bubbles (Viewport/TextArea widgets) -- an integrated,
Go-backed ecosystem Python has no bindings to. Textual is the Python
replacement: RichLog stands in for Bubbles::Viewport, Input for
Bubbles::TextArea, CSS for Lipgloss::Style, and set_interval for
Bubbletea.tick. See docs/plans/python_port/11_tui.md for the full mapping.

NOTE on the Esc key: Ruby's Esc does `@turn_thread.raise(Interrupt)`,
asynchronously injecting an exception into the running turn's thread to
abort it -- including mid-HTTP-call. Python's threading model has no safe
equivalent of Thread#raise for interrupting an arbitrary running thread;
there is no way to safely abort a blocking urllib call from outside the
thread running it. Esc is accepted as a keypress here but is a deliberate,
documented no-op while a turn is active -- not a silent gap, and not worked
around with a fragile cooperative-cancellation scheme that still couldn't
abort an in-flight request.
"""
import time
from queue import Queue

from textual.app import App, ComposeResult
from textual.widgets import Input, RichLog, Static

from .agent import Agent

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
TICK_SECONDS = 0.06

# Thresholds for context-usage colour coding.
CTX_WARN_PCT = 70
CTX_ALERT_PCT = 85


def _idle_live():
    return {
        "active": False,
        "spinner_idx": 0,
        "start_time": None,
        "elapsed": 0,
        "current_action": "idle",
        "iteration": 0,
        "tool_call_count": 0,
        "turn_input_tokens": 0,
        "turn_output_tokens": 0,
    }


class Tui(App):
    """The Textual App itself -- a single class fills both the "wrapper"
    and "Bubbletea::Model" roles Ruby splits only nominally (Tui *is* the
    model bubbletea drives, matching Ruby's own single-class design).
    """

    CSS = """
    Screen {
        layout: vertical;
    }
    #conversation {
        height: 1fr;
        border: none;
    }
    #progress {
        height: 1;
        color: cyan;
    }
    #prompt-input {
        height: 1;
        border: none;
    }
    #status {
        height: 1;
        background: #808080;
        color: white;
    }
    """

    def __init__(self, repl) -> None:
        super().__init__()
        self._repl = repl
        # Named _ctx, not _context: Textual's own App class defines a
        # _context() contextmanager method (used throughout its core event
        # loop) -- assigning a plain attribute called _context here would
        # silently shadow it and hang the app with no error.
        self._ctx = repl.context

        self._conversation = []
        self._dirty = True
        self._turn_count = 0

        self._events = Queue()
        self._live = _idle_live()

    # ---------- Textual widget tree ----------------------------------------

    def compose(self) -> ComposeResult:
        yield RichLog(id="conversation", markup=False, auto_scroll=True)
        yield Static("", id="progress")
        yield Input(placeholder="Type a message…", id="prompt-input")
        yield Static("", id="status")

    def on_mount(self) -> None:
        self._conversation.append(self._repl.banner())

        self._repl.on_output(self._on_output)
        self._repl.logger.subscribe(self._events.put)

        self.query_one("#prompt-input", Input).focus()
        self.set_interval(TICK_SECONDS, self._on_tick)
        self._sync_conversation()
        self._render_progress()
        self._render_status()

    # ---------- REPL output / logger event plumbing ------------------------

    # Called from Repl.run_turn -- which may be executing on the background
    # worker thread. Only touches a plain list + bool, both safe to mutate
    # from any thread under the GIL; the actual widget update happens later,
    # from _on_tick, which always runs on the app's own event loop.
    def _on_output(self, text) -> None:
        self._conversation.append(str(text))
        self._dirty = True

    def _on_tick(self) -> None:
        self._drain_events()
        if self._live["active"]:
            self._live["spinner_idx"] = (self._live["spinner_idx"] + 1) % len(SPINNER_FRAMES)
            if self._live["start_time"] is not None:
                self._live["elapsed"] = time.monotonic() - self._live["start_time"]
        if self._dirty:
            self._sync_conversation()
        self._render_progress()
        self._render_status()

    def _drain_events(self) -> None:
        while True:
            try:
                event = self._events.get_nowait()
            except Exception:
                break
            self._handle_event(event)

    def _handle_event(self, event) -> None:
        phase = event.get("phase")

        if phase == "iteration":
            self._live["iteration"] = int(event.get("n") or 0)
            self._live["current_action"] = "Thinking…"

        elif phase == "tool_call":
            name = event.get("name")
            self._live["current_action"] = "Calling tool: {}".format(name)
            self._live["tool_call_count"] += 1

        elif phase == "tool_result":
            self._live["current_action"] = "Awaiting result…"

        elif phase == "response":
            usage = event.get("usage")
            if usage:
                self._live["turn_input_tokens"] += int(usage.get("input_tokens") or 0)
                self._live["turn_output_tokens"] += int(usage.get("output_tokens") or 0)

        elif phase == "compaction":
            dropped = event.get("dropped")
            self._conversation.append("[context compacted — {} messages dropped to free space]".format(dropped))
            self._dirty = True

        elif phase == "turn_complete":
            # Not the real Logger's own "turn_end" event (Agent.run() emits
            # that once per turn already, via logger.turn_end) -- this is
            # our own worker-thread-finished signal, deliberately a
            # different name so the two don't double-count.
            self._live["active"] = False
            self._turn_count += 1

        elif phase == "turn_interrupted":
            # Ruby's equivalent fires when Thread#raise(Interrupt) actually
            # lands after Esc. Kept for structural parity with Ruby's
            # handle_event, but unreachable here: this port's Esc is a
            # documented no-op (see the module docstring), so
            # _run_turn_worker never has an Interrupt to catch and never
            # emits this phase.
            self._conversation.append("[interrupted]")
            self._dirty = True

        elif phase == "turn_error":
            err = event.get("error")
            self._live["active"] = False
            self._conversation.append("[error] {}".format(err))
            self._dirty = True

    # ---------- rendering ----------------------------------------------

    def _sync_conversation(self) -> None:
        log_widget = self.query_one("#conversation", RichLog)
        log_widget.clear()
        for line in self._conversation:
            log_widget.write(line)
        self._dirty = False

    def _render_progress(self) -> None:
        widget = self.query_one("#progress", Static)
        if self._live["active"]:
            frame = SPINNER_FRAMES[self._live["spinner_idx"]]
            action = self._live["current_action"]
            iteration = self._live["iteration"]
            max_iterations = Agent.MAX_ITERATIONS
            secs = int(self._live["elapsed"])
            itok = self._fmt_tokens(self._live["turn_input_tokens"])
            otok = self._fmt_tokens(self._live["turn_output_tokens"])
            calls = self._live["tool_call_count"]
            widget.update(
                "{} {}  (iter {}/{} · {}s · ↑ {} · ↓ {} · {} calls)".format(
                    frame, action, iteration, max_iterations, secs, itok, otok, calls
                )
            )
        else:
            pct = self._ctx.usage_pct()
            color = self._ctx_color(pct)
            used = self._fmt_tokens(self._ctx.current_tokens)
            max_tokens = self._fmt_tokens(self._ctx.context_window)
            widget.update(
                "[{}]  [ready]   ctx {} / {} ({}%)   {} turns[/{}]".format(
                    color, used, max_tokens, pct, self._turn_count, color
                )
            )

    def _render_status(self) -> None:
        widget = self.query_one("#status", Static)
        ver = self._repl.version or __import__("boukensha").VERSION
        model = self._repl.model or "(model)"
        pct = self._ctx.usage_pct()
        used = self._fmt_tokens(self._ctx.current_tokens)
        max_tokens = self._fmt_tokens(self._ctx.context_window)
        tools = self._ctx.tool_count()
        clock = time.strftime("%H:%M:%S")

        ctx_indicator = " ⚠ " if pct >= CTX_ALERT_PCT else " "
        bar = " boukensha v{} · {}  ·  ctx {}/{} ({}%){}·  {} tools  ·  {} ".format(
            ver, model, used, max_tokens, pct, ctx_indicator, tools, clock
        )
        widget.update(bar)

    @staticmethod
    def _ctx_color(pct) -> str:
        if pct >= CTX_ALERT_PCT:
            return "red"
        if pct >= CTX_WARN_PCT:
            return "yellow"
        return "grey53"

    @staticmethod
    def _fmt_tokens(n) -> str:
        n = int(n or 0)
        return "{}k".format(round(n / 1000.0, 1)) if n >= 1000 else str(n)

    # ---------- keyboard -------------------------------------------------

    def on_key(self, event) -> None:
        key = event.key

        if key in ("ctrl+c", "ctrl+d"):
            self.exit()
            event.stop()
        elif key == "escape":
            # Deliberate no-op -- see the module docstring for why Python
            # can't safely interrupt a running turn's thread the way Ruby's
            # Thread#raise(Interrupt) does.
            event.stop()
        elif key == "ctrl+l":
            self._repl.handle_command("/clear")
            self._turn_count = 0
            event.stop()
        elif key == "pageup":
            self.query_one("#conversation", RichLog).scroll_up()
            event.stop()
        elif key == "pagedown":
            self.query_one("#conversation", RichLog).scroll_down()
            event.stop()

    def on_input_submitted(self, message: Input.Submitted) -> None:
        self._submit_input(message.value)
        message.input.value = ""

    def _submit_input(self, raw_input: str) -> None:
        text = raw_input.strip()
        if not text:
            return

        if text.startswith("/"):
            result = self._repl.handle_command(text)
            if result == "quit":
                self.exit()
                return
            if text == "/clear":
                self._turn_count = 0
        else:
            self._conversation.append("> {}".format(text))
            self._dirty = True
            self._launch_turn(text)

    # ---------- agent worker ---------------------------------------------

    def _launch_turn(self, text: str) -> None:
        self._live = _idle_live()
        self._live["active"] = True
        self._live["start_time"] = time.monotonic()
        self._live["current_action"] = "Thinking…"

        self.run_worker(lambda: self._run_turn_worker(text), thread=True, exclusive=False)

    def _run_turn_worker(self, text: str) -> None:
        try:
            self._repl.run_turn(text)
        except Exception as e:  # noqa: BLE001 -- mirrors Ruby's bare `rescue`
            self._repl.logger.error(e, where="Tui._run_turn_worker", operation="run_turn")
            self._events.put({"phase": "turn_error", "error": str(e)})
        finally:
            self._events.put({"phase": "turn_complete"})
