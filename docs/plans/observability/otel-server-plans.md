# Observability Plan — OTel Collector + Boukensha Log Streaming + Cloud-Native Viewer

## Scope

Stand up an OpenTelemetry Collector, stream Boukensha's existing session
logs to it **in addition to** the `.boukensha/sessions/*.jsonl` files it
already writes (no change to that file-based logging — it stays the
source of truth `log_viz` and everything else already depends on), and
then stand up the most common cloud-native stack for actually *viewing*
those logs once they reach the collector.

This is infrastructure, not a Ruby/Python port — it lives under
`week2_observability/observability/` (already created, currently empty)
as a self-contained Docker Compose stack, and touches none of the
per-step `week1_baseline/{ruby,python}/NN_*/lib` boukensha packages.

## Current state (confirmed)

- Every Boukensha step (`Boukensha::Logger` in Ruby, its Python port)
  writes one JSON object per line to
  `.boukensha/sessions/<session_id>.jsonl`, one file per session, via
  plain `File.open(..., "a")` + `puts JSON.generate(...)` — no network
  I/O, no OTel awareness, nothing to configure per step
  (`week1_baseline/ruby/12_context/lib/boukensha/logger.rb:100-104`).
- Each line is a flat JSON object: `phase` (`session_start`, `turn`,
  `iteration`, `plan`, `prompt`, `response`, `tool_call`, `tool_result`,
  `turn_end`, `compaction`, `reasoning`, `limit_reached`, `raw`), plus
  phase-specific fields, plus `session_id` and `at` (local ISO-8601 with
  UTC offset, second precision) merged onto every line. Confirmed against
  a real captured session
  (`.boukensha/sessions/20260725T230144Z-426b1a0e.jsonl`).
- `week1_baseline/log_viz` is a Sinatra app that reads these `.jsonl`
  files directly (no intermediary) and renders them as a chat transcript.
  It keeps working unchanged under this plan — it's a second, independent
  consumer of the same files, not something this plan replaces.
- `week2_observability/observability/` exists and is empty — the natural
  home for the new Compose stack. `week2_capable/.keep` was removed in
  favor of this directory (see `git status`), so this is this week's
  intended working area.
- Docker 29.6.1 and Docker Compose v5.2.0 are already installed
  (`docker --version` / `docker compose version` both resolve).

## Architecture decision: tail the files, don't touch the logger

Two ways to get these logs into an OTel pipeline:

1. **Filelog receiver tails `.boukensha/sessions/*.jsonl`** — the
   Collector reads the files, parses each line as JSON, maps fields to
   OTel log record attributes, exports. Zero changes to Boukensha code.
2. **Instrument `Logger#write_log` directly** with an OTel Logs SDK
   exporter, dual-writing to file + OTLP at write time.

**Going with (1).** Every step folder from `00_config` through
`12_context` (and both languages) has its own copy of `logger.rb` /
`logger.py` — that's the repo's whole point, per-step duplication for the
tutorial. Option (2) means threading an OTel SDK dependency and export
call through every one of those copies, in two languages, for a
mechanism orthogonal to what each step is actually teaching. Option (1)
is also just the standard cloud-native pattern for getting logs out of
an app that wasn't written with a telemetry SDK in mind (the same shape
as Promtail/Fluent Bit tailing container log files in production) — it's
not a workaround, it's the idiomatic answer here. It does mean the
collector is reading whichever `.boukensha/sessions/` directory it's
pointed at (repo root, by default, per `.boukensharc`), so it needs a
bind mount, not in-process access.

Revisit (2) only if we later want *real-time* export with zero tailing
lag, or per-event severity/attributes decided in code rather than
inferred by the collector — noted as a stretch item, not needed for the
core ask.

## Phase 1 — OpenTelemetry Collector, logs only, verified into stdout

Get a collector running, tailing real session files, and prove log
records come out the other end — before wiring up any storage backend.

**Compose service** (`week2_observability/observability/docker-compose.yml`):
using `otel/opentelemetry-collector-contrib` (not the core image — the
`filelog` receiver only ships in contrib), bind-mounting the repo's
`.boukensha/sessions/` read-only.

**Collector config** (`week2_observability/observability/otel-collector-config.yaml`):
- `receivers.filelog`: `include: [/var/log/boukensha/sessions/*.jsonl]`,
  `start_at: beginning` for the first run, operators:
  - `json_parser` to parse each line into the body.
  - `move` the parsed `at` field to the log record timestamp
    (`time_parser` operator, layout matching Ruby's `iso8601`/Python's
    `isoformat(timespec="seconds")` output, e.g.
    `2026-07-25T19:02:08-04:00`).
  - `move` `session_id` to a resource attribute (groups log records by
    session the way a `service.instance.id` would).
  - `move` `phase` to a log attribute, and derive `severity` from it: a
    `tool_result` with `ok: false` → `WARN`; `limit_reached` → `WARN`;
    everything else → `INFO`. (Small `router`/`severity_parser`
    operator chain — exact rules are a Phase 1 implementation detail,
    not an open design question.)
- `processors`: `batch` (default), `resource` (attach a static
  `service.name: boukensha` so it's identifiable once other things start
  sending telemetry to the same collector).
- `exporters`: start with `debug` (verbosity: detailed) only — stdout,
  no backend dependency yet.
- `service.pipelines.logs`: `filelog` → `[resource, batch]` → `debug`.

**Verification**: run any existing Boukensha example
(`week1_baseline/bin/ruby/12_context` or the Python equivalent) to
produce a fresh session file, `docker compose up`, confirm the
collector's stdout shows parsed log records with correct
`session_id`/`phase`/timestamp — including a run against an
**already-existing** session file to confirm `start_at: beginning`
picks up history, not just new writes.

## Phase 2 — persist the offset, don't replay on every restart

Add a `file_storage` extension (`otel-collector-file-storage` volume) and
wire it into the `filelog` receiver's `storage` field, so restarting the
collector doesn't re-ingest every historical session from scratch. Minor,
but worth doing before pointing at a real backend — otherwise every
Grafana/Loki restart in Phase 3 floods the store with duplicates.

## Phase 3 — Grafana + Loki (the log-viewing stack)

This is the "most common cloud-native tool" answer for *logs*
specifically: **Grafana Loki** for storage/indexing (log-oriented,
label-based, built to sit behind an OTel Collector) and **Grafana** for
the UI. This pairing — plus Tempo for traces and
Prometheus/Mimir for metrics — is generally called the "LGTM stack" and
is the de facto standard OSS cloud-native observability stack (the
alternative most people would name instead is the Elastic/ELK stack;
Loki is the lighter-weight, more purpose-built-for-this option and the
better fit for a learning stack in this repo — flagged as an open
question below in case you'd rather do ELK).

**Compose additions:**
- `loki` (single-binary mode, local filesystem chunk/index storage —
  fine at this scale, no need for object storage or microservices mode).
  Data volume gitignored (add to `.gitignore`), matching the existing
  `.venv/`/`.env` local-state convention.
- `grafana`, with Loki pre-provisioned as a datasource via Grafana's
  provisioning YAML (`GF_PATHS_PROVISIONING`) rather than manual
  click-ops, so `docker compose up` gives a working datasource
  immediately.

**Collector wiring**: add an `otlphttp/loki` exporter pointed at Loki's
native OTLP logs endpoint (`http://loki:3100/otlp/v1/logs` — Loki speaks
OTLP directly since 3.x, no separate `loki` exporter/label-mapping
config needed), add it to the `logs` pipeline alongside `debug` (keep
`debug` around for now — cheap and useful while iterating).

**Grafana verification:**
- Explore view, LogQL query filtered by the `service.name="boukensha"`
  resource attribute, confirm log lines render with `session_id`/`phase`
  as filterable labels.
- One simple dashboard: log volume by `phase` over time, and a table of
  `response`-phase records (task/provider/model/cost_usd/tokens) — the
  same data `log_viz`'s session-list page already summarizes, now queried
  through LogQL instead of parsed from the file directly. This isn't
  meant to replace `log_viz`'s per-session transcript view (Loki is bad
  at "show me one ordered conversation nicely formatted" — that's exactly
  what `log_viz` is for); it's meant for the things `log_viz` can't do:
  cross-session search/filtering and aggregate views.

## Phase 4 (stretch, optional) — traces and metrics

Not required for "stream logs / view logs," but flagged since "the most
common cloud-native observability tools" plural naturally includes
tracing, and Boukensha's own event shape maps onto it unusually well:
`session_start`→`turn_end` is a trace, each `turn`/`iteration` a span,
`tool_call`/`tool_result` pairs are child spans or span events. If
pursued later:
- Add a `transform` processor deriving spans from the `turn`/`iteration`
  nesting (or, if that proves awkward in the collector, this is where
  revisiting the "instrument the logger directly" alternative from the
  Architecture section would actually pay for itself — real span
  start/end needs real start/end timestamps, which tailing after the
  fact can only approximate from consecutive log lines).
- **Tempo** for trace storage, **Prometheus** for metrics (token counts,
  cost_usd as counters/histograms, extracted via a `spanmetrics`
  connector or a parallel `metrics` pipeline).
- Same Grafana instance, two more datasources.

Explicitly out of scope unless you want it — the plan above is complete
and independently useful without this phase.

## Task list

1. Create `week2_observability/observability/docker-compose.yml` with
   `otel-collector` (contrib image) + a bind mount of `.boukensha/sessions/`.
2. Write `otel-collector-config.yaml`: `filelog` receiver (`json_parser`,
   `time_parser`, `session_id`→resource attribute, `phase`→attribute +
   derived severity), `resource`/`batch` processors, `debug` exporter,
   `logs` pipeline.
3. Verify Phase 1 against both an existing and a freshly-generated
   session file.
4. Add `file_storage` extension + volume; wire into the `filelog`
   receiver's `storage` field; verify a collector restart doesn't
   re-ingest.
5. Add `loki` and `grafana` services to the Compose file; provision the
   Loki datasource in Grafana via YAML, not manual setup.
6. Add `otlphttp/loki` exporter to the collector config, targeting
   Loki's native `/otlp/v1/logs` endpoint; add to the `logs` pipeline.
7. Gitignore Loki/Grafana local data volumes.
8. Verify in Grafana: Explore query by `session_id`/`phase`; build the
   log-volume-by-phase and response-summary-table dashboard panels.
9. Write a short README in `week2_observability/observability/` covering
   `docker compose up`, ports, and how to point the stack at a
   non-default `.boukensha` dir (mirroring `log_viz`'s
   `LOG_VIZ_SESSIONS_DIR` env var convention).
10. (Stretch, only if you confirm you want it) Phase 4: traces/metrics,
    Tempo + Prometheus.

## Open questions for you

1. **Loki vs. Elastic/ELK.** This plan defaults to Grafana Loki as "the"
   common cloud-native log stack (lighter, purpose-built, pairs directly
   with an OTel Collector). If you specifically want the Elastic stack
   instead (Elasticsearch + Kibana, via the collector's `elasticsearch`
   exporter), say so and Phase 3 gets rewritten around that instead.
- use the Loki log stack.
2. **Which `.boukensha/sessions` directory to tail.** The repo root's
   `.boukensha/` (currently pointed at by `.boukensharc`,
   `boukensha_path: .../ruby/12_context`) is the obvious default, but
   confirm that's the one you want streamed, vs. some other step's
   session directory.
- Tail the `.boukensha/sessions` directory.
3. **Whether Phase 4 (traces/metrics) is wanted at all**, given the
   original ask was specifically about logs.
- include Phase 4 in this plan.   
