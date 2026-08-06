"""Flask app: sessions (live-tailing transcript + waterfall), a top-level
Errors page, and the raw MUD command log -- three views over the durable
log tree every boukensha instance already writes under BOUKENSHA_DIR.
"""
import json
import os
import time
from pathlib import Path

from flask import Flask, Response, abort, render_template, request, stream_with_context

from . import ansi, errors as errors_mod, mud_log as mud_log_mod, sessions, spans as spans_mod

HOME_BOUKENSHA_DIR = str(Path.home() / ".boukensha")
# .../week3_capable/python/logging_monitor/logging_monitor/server.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_BOUKENSHA_DIR = REPO_ROOT / ".boukensha"
DEFAULT_PORT = 4568
DEFAULT_BIND = "localhost"
POLL_INTERVAL_S = 0.5


def resolve_boukensha_dir():
    # boukensha/config.py's Config only ever checks BOUKENSHA_DIR, falling
    # back to ~/.boukensha -- fine for a real install, but this repo's own
    # sessions/settings.yaml/errors.jsonl all live at <repo root>/.boukensha,
    # not ~/.boukensha. Forgetting to export BOUKENSHA_DIR before launching
    # silently pointed this app at an empty ~/.boukensha. Prefer, in order:
    # (1) an explicit BOUKENSHA_DIR env var -- always wins, (2) this repo's
    # own .boukensha if it exists -- the common case for anyone running
    # logging_monitor from inside this checkout, (3) ~/.boukensha, matching
    # Config's own default for parity when neither of the above applies.
    env_dir = os.environ.get("BOUKENSHA_DIR")
    if env_dir:
        return str(Path(env_dir).expanduser().resolve())
    if REPO_BOUKENSHA_DIR.is_dir():
        return str(REPO_BOUKENSHA_DIR)
    return str(Path(HOME_BOUKENSHA_DIR).expanduser().resolve())


def create_app(boukensha_dir=None):
    # static/ lives at the top of the package (sibling of logging_monitor/
    # and tests/), not inside logging_monitor/ itself -- point Flask at it
    # explicitly rather than relying on its default (relative to this
    # module's own directory).
    static_dir = str(Path(__file__).resolve().parent.parent / "static")
    app = Flask(__name__, static_folder=static_dir, static_url_path="/static")
    app.config["BOUKENSHA_DIR"] = boukensha_dir or resolve_boukensha_dir()

    app.jinja_env.filters["ansi_html"] = ansi.to_html
    app.jinja_env.filters["text_html"] = ansi.escape_html
    app.jinja_env.filters["fmt_tokens"] = _fmt_tokens
    app.jinja_env.filters["fmt_cost"] = _fmt_cost
    app.jinja_env.filters["truncate_flat"] = _truncate

    @app.get("/")
    def index():
        boukensha_dir = app.config["BOUKENSHA_DIR"]
        summaries = []
        for path in sessions.session_paths(boukensha_dir):
            try:
                summaries.append(sessions.Session.load(path).to_summary())
            except (OSError, json.JSONDecodeError):
                continue
        return render_template("index.html", sessions=summaries, boukensha_dir=boukensha_dir)

    @app.get("/sessions/<session_id>")
    def session_detail(session_id):
        boukensha_dir = app.config["BOUKENSHA_DIR"]
        path = sessions.session_path(boukensha_dir, session_id)
        if not os.path.isfile(path):
            abort(404, "Session not found: {}".format(session_id))

        session = sessions.Session.load(path)
        waterfall_svg = spans_mod.render_svg(spans_mod.build_spans(_read_events(path)))
        return render_template("session.html", session=session, waterfall_svg=waterfall_svg)

    @app.get("/sessions/<session_id>/waterfall")
    def session_waterfall(session_id):
        # Polled every few seconds by session.html while the SSE transcript
        # stream is live, so the waterfall keeps growing new turns/spans as
        # a session that's still running produces them -- without
        # duplicating spans.py's reconstruction logic in JS.
        boukensha_dir = app.config["BOUKENSHA_DIR"]
        path = sessions.session_path(boukensha_dir, session_id)
        if not os.path.isfile(path):
            abort(404, "Session not found: {}".format(session_id))

        svg = spans_mod.render_svg(spans_mod.build_spans(_read_events(path)))
        return Response(svg, mimetype="image/svg+xml")

    @app.get("/sessions/<session_id>/stream")
    def session_stream(session_id):
        boukensha_dir = app.config["BOUKENSHA_DIR"]
        path = sessions.session_path(boukensha_dir, session_id)
        if not os.path.isfile(path):
            abort(404, "Session not found: {}".format(session_id))

        def generate():
            state = sessions.ParseState()
            with open(path) as f:
                # The initial GET /sessions/<id> already server-rendered every
                # entry currently in the file -- replaying them here too would
                # duplicate the whole transcript in the DOM. Advance `state`
                # (turn/iteration/pending_calls/prev_dt) silently past
                # whatever's already on disk, using the exact same parser
                # sessions.Session.parse() uses, so the *first* genuinely new
                # entry we do yield gets the right turn/iteration and the
                # right duration_ms (gap since the real previous line, not
                # since this request started).
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    sessions.parse_event(state, event)

                # Then poll for new lines appended after this point -- this is
                # what makes "sit on the page and watch it update" real.
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(POLL_INTERVAL_S)
                        continue
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    entry = sessions.parse_event(state, event)
                    if entry is not None:
                        yield _sse_entry(entry)

        # render_template inside the generator needs an active app/request
        # context, which a bare generator loses the moment the view
        # function returns and Flask moves on -- stream_with_context keeps
        # it bound for as long as the client stays connected and consuming.
        return Response(stream_with_context(generate()), mimetype="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    @app.get("/errors")
    def errors_page():
        boukensha_dir = app.config["BOUKENSHA_DIR"]
        return render_template("errors.html", errors=errors_mod.load_all(boukensha_dir))

    @app.get("/mud")
    def mud_page():
        boukensha_dir = app.config["BOUKENSHA_DIR"]
        return render_template("mud.html", entries=mud_log_mod.load_entries(boukensha_dir))

    return app


def _read_events(path):
    with open(path) as f:
        events = []
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events


def _sse_entry(entry):
    html = render_template("_entry.html", entry=entry)
    # SSE payloads are newline-delimited; a multi-line HTML fragment has to
    # be sent as multiple `data:` lines, or everything after the first
    # newline is silently dropped by the EventSource parser.
    data_lines = "\n".join("data: {}".format(line) for line in html.splitlines())
    return "{}\n\n".format(data_lines)


def _fmt_tokens(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "0"
    return "{:.1f}k".format(n / 1000.0) if n >= 1000 else str(n)


def _fmt_cost(n):
    return "—" if n is None else "${:.4f}".format(n)


def _truncate(text, length=100):
    flat = " ".join(str(text or "").split())
    return (flat[:length] + "…") if len(flat) > length else flat


def main():
    boukensha_dir = resolve_boukensha_dir()
    app = create_app(boukensha_dir)
    port = int(os.environ.get("LOGGING_MONITOR_PORT", DEFAULT_PORT))
    bind = os.environ.get("LOGGING_MONITOR_BIND", DEFAULT_BIND)
    app.run(host=bind, port=port, threaded=True)


if __name__ == "__main__":
    main()
