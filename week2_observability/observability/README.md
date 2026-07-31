# Boukensha Observability Stack

An OpenTelemetry Collector that tails `.boukensha/sessions/*.jsonl` and
streams it into a local Grafana + Loki + Tempo + Prometheus stack, so
Boukensha session logs are viewable in the same cloud-native tools used
in production observability setups — in addition to (not instead of)
the existing `.jsonl` files, which `week1_baseline/log_viz` still reads
directly. See `docs/plans/observability/otel-server-plans.md` for the
design rationale.

## Run it

```sh
docker compose up -d
```

First start backfills every existing session under `.boukensha/sessions/`
into Loki — give it 30-60s to finish (`docker compose logs -f otel-collector`
to watch). Restarting the collector later does **not** replay
already-ingested files (offsets persist in the `otel-file-storage`
volume) or duplicate metrics/logs already in Loki.

| Service | URL | Notes |
|---|---|---|
| Grafana | http://localhost:3000 | Anonymous access, Admin role — local-only stack, no login needed |
| Loki | http://localhost:3100 | Log storage; queried through Grafana, not usually directly |
| Tempo | http://localhost:3200 | Trace storage |
| Prometheus | http://localhost:9090 | Metrics |
| OTel Collector | localhost:4317 (gRPC) / :4318 (HTTP) | OTLP ingest — traces from `scripts/session_to_traces.py` land here |

Open Grafana → Dashboards → **Boukensha Logs** for the pre-built view.

To point at a different `.boukensha/` (e.g. a different step folder),
set `BOUKENSHA_SESSIONS_DIR` before starting:

```sh
BOUKENSHA_SESSIONS_DIR=/path/to/other/.boukensha/sessions docker compose up -d
```

## What's in the stack

- **otel-collector** (`otel-collector-config.yaml`) — `filelog` receiver
  tails the session `.jsonl` files, parses each line as JSON, and turns
  it into a structured OTel log record: `session_id` becomes a resource
  attribute, `phase` a log attribute, `at` the record timestamp, and
  severity is inferred (`tool_result` with `ok:false`, or
  `limit_reached`, get `WARN`; everything else `INFO`). No Boukensha code
  is touched — this reads the same files `log_viz` reads, from outside.
  It also runs an `otlp` receiver (4317/4318) for the trace-shipper
  script, and a `count` connector that turns the logs pipeline into
  Prometheus counters for free (Phase 4).
- **loki** (`loki-config.yaml`) — receives logs via its native OTLP
  endpoint (`/otlp/v1/logs`). See "Loki tuning" below for why the default
  config needed changes.
- **tempo** (`tempo-config.yaml`) — receives traces from
  `scripts/session_to_traces.py` via the collector. Pinned to `2.6.1`,
  not `latest` — Tempo 3.x restructured its top-level config keys
  (`ingester`/`compactor` no longer parse the same way) and 2.x is the
  stable, documented shape this config uses.
- **prometheus** (`prometheus.yml`) — scrapes the collector's
  `count`-connector metrics off `:8889`.
- **grafana** — Loki/Tempo/Prometheus datasources and the **Boukensha
  Logs** dashboard are provisioned automatically from
  `grafana/provisioning/` and `grafana/dashboards/`; nothing to click
  through by hand.

All images are pinned to specific versions (not `:latest`) for
reproducibility.

## Loki tuning (why the config isn't the bundled default)

A first-run backfill of a whole `.boukensha/sessions/` history is
bursty and *historically timestamped* (old `at` values, not "now") in a
way Loki's out-of-the-box defaults don't expect:

- **`session_id` is promoted to an actual Loki index label**
  (`limits_config.otlp_config`), not left as structured metadata. Every
  session's events funnel through as its own file, read concurrently
  with every other session's file — without a per-session label they'd
  all land in one shared stream and violate Loki's (mostly-)monotonic
  per-stream timestamp ordering, and most of a bulk backfill gets
  silently dropped as "entry too far behind". Cardinality is bounded
  (one label value per session, not per-request), so this is the
  correct fix, not just a workaround.
- **`reject_old_samples_max_age` raised to a year** — default (7d) drops
  anything older, and Boukensha history routinely is.
- **`ingestion_rate_mb`/`ingestion_burst_size_mb` raised** — default
  (~4MB/s) rate-limited a full-history burst into the ingester.
- **`grpc_server_max_recv_msg_size` raised to 16MB** — the collector's
  batch processor is capped at 100-200 log records per batch
  (`otel-collector-config.yaml`), but some MUD room-description bodies
  are multi-KB each, and one big batch still occasionally exceeded
  Loki's 4MB default gRPC message limit.
- **`ingester.chunk_idle_period` shortened to 30s, `querier.query_ingesters_within`
  widened to 168h** — Loki only checks its in-memory (unflushed)
  ingester data for *recent* time-range queries; a query about
  historically-timestamped backfilled data would otherwise only see
  already-flushed chunks, leaving small, still-unflushed sessions
  invisible for up to the default flush interval.

None of this is exotic tuning — it's what Loki's own docs describe for
backfilling historical data. It's called out here because it's easy to
assume "logs into Loki" just works out of the box and lose real data
silently otherwise (this stack initially did, until each of the above
was tracked down and fixed).

## Tempo tuning

- **`metrics_generator` (ring + `local-blocks` processor) is enabled.**
  Without it, opening Explore's trace search view in Grafana 500s with
  `error finding generators in Querier.queryRangeRecent: empty ring` —
  Grafana's search page always fires an ad-hoc TraceQL metrics query
  (the rate/error-rate/duration mini-graph above results) that needs a
  running metrics-generator, and Tempo has none configured by default.
  `ring.kvstore.store: inmemory` is required too — without it the
  generator never registers and the same "empty ring" error persists.
- **`overrides.defaults.metrics_generator.ingestion_time_range_slack`
  raised to a year** — same shape as the Loki age limit above: the
  generator normally only accepts spans within a small slack window of
  "now" (it's built for live dashboards), and `session_to_traces.py`
  ships spans carrying the session's *original* historical timestamps.
  Without this, every span gets silently counted in
  `tempo_metrics_generator_spans_discarded_total{reason="outside_metrics_ingestion_slack"}`.
- **`ingester.max_block_duration` shortened to 30s, `storage.trace.blocklist_poll`
  shortened to 10s** — so a trace shipped via the script becomes visible
  to Explore's trace *search* within under a minute instead of up to 5.

**Search vs. trace-by-ID lookup, and why they behave differently for
shipped traces**: a Tempo block's own start/end metadata (used to decide
which blocks even get scanned for a given time-range search) is set from
when spans were *received*, not the timestamp value inside them — so a
just-shipped trace's block is stamped with today's date, while the spans
inside it carry the session's real, older `at` timestamps. Search
filters on both, and those two clocks disagree by design here, so
**time-range search may not find a shipped trace no matter what window
you pick**. Looking it up by the exact trace ID printed by the script
(Explore → Tempo datasource → "TraceID" query type) always works —
that path skips time-range filtering entirely. This is a structural
consequence of shipping historically-timestamped spans into a system
built for near-real-time ingestion, not a bug tuning can fix further.

## Prometheus / count connector — known limitation, read before relying on it

Two real bugs were found and fixed here; a third turned out to be a
structural limitation rather than something more config can solve, and
is why this metric is **not** an accurate historical total:

- **Fixed — `count` connector emits a delta per batch, not a running
  total.** Confirmed against its own source: every `ConsumeLogs` call
  creates a fresh internal counter, counts just that batch, exports it,
  and discards it — no state carried across calls. Since the prometheus
  exporter doesn't itself accumulate deltas, each new batch's count was
  silently *replacing* the previously-exposed value rather than adding
  to it (verified directly: a controlled 5-event burst dropped the
  exposed total from the real backfill's count down to 5). Fixed by
  adding the `deltatocumulative` processor to the `metrics` pipeline,
  which holds the running sum itself.
- **Fixed — `metric_expiration`.** The prometheus exporter's default 5m
  means a series untouched for 5 minutes stops being served. Grouping
  the connector's output by `phase` only (not `session_id`) means a
  series like `phase="response"` is touched continuously by every
  session rather than once ever; `metric_expiration` is also widened to
  24h as a second safety net for genuinely idle stretches.
- **Not fixed — resource-identity collision undercounts a bulk backfill.**
  `session_id` is an OTel *resource* attribute (required — see the Loki
  section above), so each session's log records carry a different
  resource. The `count` connector's output metric carries that resource
  forward, and the prometheus exporter drops resource attributes from
  its label set — so distinct sessions' counters collapse onto the
  identical `{phase="..."}` Prometheus series, and the exporter keeps
  only the last one it processed rather than summing across sessions.
  Concretely: after a full backfill of the real `.boukensha/sessions/`
  history (confirmed via Loki's own ingestion counter: exactly the
  correct number of lines received, zero discards), the count
  connector's totals came out roughly **20-60x lower** than the true
  event count. Branching the pipeline (via a `forward` connector) to
  strip `session_id` before the data reaches `count` was tried and did
  reduce, but did not eliminate, the undercount — some further loss
  happened elsewhere in that chain that wasn't pinned down, and adding
  the extra pipeline hop wasn't worth it for the accuracy it didn't
  reliably deliver. **Treat this metric as "is there recent activity,
  roughly how much" for live use, never as a historical total** — Loki
  (panel 1 below) is the accurate source for that, confirmed repeatedly
  against real backfills with matching, exact totals.

## Dashboard panels

1. **Log volume by phase** (Loki) — `sum by (phase) (count_over_time(...))`.
   This is the accurate one; use it for anything historical.
2. **Response events** (Loki, table) — every `response`-phase log line
   parsed (`| json`) into columns: session, task, provider, model,
   cost_usd, tokens, stop_reason. The same data `log_viz`'s session list
   summarizes, queryable across sessions instead of one file at a time.
3. **Event rate by phase** (Prometheus) — from the collector's `count`
   connector. Also **resets on every otel-collector restart** (in-memory,
   not persisted) on top of the undercounting above — treat as a rough
   "is Boukensha active right now" signal only, never as a total. See
   "Prometheus / count connector" above for the full story.

`log_viz` (`week1_baseline/log_viz`) is still the right tool for reading
one session as a transcript — this stack is for cross-session
search/filtering and aggregate views, not a replacement.

## Traces (Phase 4, on demand)

Boukensha's `session_start` → `turn` → `iteration` → `tool_call`/
`tool_result` event shape maps naturally onto a trace, but nothing
here derives spans automatically from the tailed logs — reconstructing
real span start/end times from a bulk historical backfill isn't
something the collector can do well after the fact (see
`docs/plans/observability/otel-server-plans.md`, Phase 4). Instead,
run the standalone converter against one session file:

```sh
python3 scripts/session_to_traces.py path/to/session.jsonl
# or, with no argument, converts the most recently modified session:
python3 scripts/session_to_traces.py
```

It reconstructs an approximate trace (session → turn → iteration →
tool_call spans, with prompt/plan/response attached as span events) from
consecutive log line timestamps and posts it to the collector's OTLP/HTTP
endpoint. Span timing is only as precise as the source `at` field
(second precision, marks when an event was *logged* — not real span
boundaries), so treat this as a way to browse a session's shape in
Tempo, not exact timing data. No pip install needed (stdlib only).

To view it: Grafana → Explore → Tempo datasource → query type
**TraceID** → paste the ID the script printed. Don't rely on the
**Search** query type to find it by service name / time range — see
"Search vs. trace-by-ID lookup" above for why that reliably comes back
empty for shipped traces even though the trace fully exists.

## Resetting

```sh
docker compose down -v
```

drops all stored logs/traces/metrics/Grafana state and starts clean
next `up`. (Data lives in Docker-managed named volumes, not the
repo tree — nothing here needs a `.gitignore` entry.)
