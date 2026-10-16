# rca-loadtest-utils

Tooling and results for loadtests of the Davis RCA analyzers (`dt.rca.horizontal.*`), currently the TCCA
(`TopologyCausalChainAnalyzer`) novelty detection loadtest series.

## Prerequisites

- `dtctl` with a context named **`gmg80500`**. This tenant holds the Davis analyzer execution logs and DQL query logs. The
  loadtest tenant itself (`gan7755d`) is only a filter value in the queries; you never connect to it.
- Local checkouts, needed only for interpreting results:
  - **davis** repo on `main`: `analyzer-modules/davis.analyzer.module.rca.horizontal`
  - **clusterworkloadsimulator (CWS)** repo on branch `feature/APPOBS-40874-rca-novelty-detection-setup`:
    `loadtest-config/deus/rca`

  Their location differs per machine. Ask the user if you can't find them (the original author used `~/dt-repos/<repo>`).

## Layout

| Path | What |
|---|---|
| `rca_loadtest_summary.py` | Fetches one run's metrics as JSON (stdout). Stdlib + `dtctl` only. |
| `schema.json` | Field-by-field description of the script's output. Read it before interpreting a JSON. |
| `loadtests/<series>/runs.md` | Written by the user: test setup and one `## Test N` section per run. **Source of truth for run parameters.** |
| `loadtests/<series>/tcca-task-payload.json` | TCCA task config used for the series. |
| `loadtests/<series>/run-NN.json` | Fetched result per run (zero-padded: `run-01.json`, `run-12.json`). |
| `loadtests/<series>/summary.md` | Per-run summaries, comparison and conclusions. |

Current series: `loadtests/tcca-novelty-detection/` (runs 1–12 done as of 2026-10-16).

## Workflow: adding new runs

### 1. Read the run parameters from `runs.md`
Each `## Test N` has date, start/end, **effective** start/end, pattern, size (pairs or hub callees) and metric mode.

- Use only the **effective** start/end. That's when TCCA actually saw the ingested events; start/end are when CWS ran.
- Times are **local time (Europe/Vienna)**. The script needs **UTC**. Convert per date, because DST matters: CEST = UTC+2
  until 2026-10-25, CET = UTC+1 after that. If unsure, check with
  `TZ=Europe/Vienna date -j -f "%Y-%m-%d %H:%M" "2026-10-16 15:06" +%z`.
- Skip tests whose effective times are still empty. Those are not finished yet; ask the user.
- `runs.md` is written by hand and can be wrong. Cross-check its claims against the payload and the data (e.g. it once
  said caching was enabled; the payload and the per-execution `smartscapeEdges` queries showed it was disabled).

### 2. Fetch
```bash
./rca_loadtest_summary.py --tenant gan7755d --context gmg80500 \
  --timeframe 2026-10-16T13:06:00Z/2026-10-16T13:30:00Z > loadtests/<series>/run-10.json
```
- Always pass `--context gmg80500` explicitly. Don't rely on the current dtctl context: a wrong context returns valid
  but all-zero JSON, not an error.
- **Never refetch** a run whose `run-NN.json` already exists. Use the local file. Write to a `.tmp` file and rename on
  success, so a failed fetch doesn't leave a truncated file that looks done.
- Each fetch runs 9 DQL queries in parallel and takes about a minute. Fetch runs sequentially (run it in the background
  if there are many).
- Sanity check after fetching: `runs.total` should be ≈ effective minutes × 0.8–0.96 (lower for slower runs) and `rootEventsFetched.total` > 0.
  All zeros means wrong context or timeframe.

### 3. Summarize in `summary.md`
Keep the existing structure and extend it, don't rewrite it:
1. Header: data source, config notes (TCCA payload + analyzer defaults), CWS load data shape.
2. **Overview table**, one row per run: pattern/size/mode, executions, warn %, root events/exec, PUPs, RCA open/born-closed,
   analysis avg/max, detector avg, request timeseries query CPU avg/max, total CPU, cost, extrapolated DT$/yr.
3. **One `### Run N – …` section per run**: a dashboard link line, then 2–5 sentences on what's notable.
4. **Comparison and conclusions**, numbered sections. When adding runs, compare them against existing runs and update
   the existing conclusions (confirm, refine or retract) instead of only appending.

Dashboard link per run (`[TSG][Obs] RCA - Loadtest`, tenant variable `Tenant`, UTC timeframe, `:` encoded as `%3A`):
```
https://gmg80500.dev.apps.dynatracelabs.com/ui/apps/dynatrace.dashboards/dashboard/a9eb4df8-1a86-409d-bd72-8363f96a5470#from=2026-10-16T13%3A06%3A00.000Z&to=2026-10-16T13%3A30%3A00.000Z&vfilter_Tenant=gan7755d
```

Quick look at the values that matter for comparisons:
```bash
cd loadtests/<series> && python3 -c '
import json,glob
for f in sorted(glob.glob("run-*.json")):
    d=json.load(open(f)); r=d["grailCpuTime"]["requestQueries"]
    print(f, d["runs"]["total"], d["runs"]["withWarnings"], d["pups"]["total"], d["rcaEvents"]["open"],
          d["rcaEvents"]["bornClosed"], d["rootEventsFetched"]["avgPerRun"], d["durations"]["detector"]["avgMs"],
          r["avgCpuSeconds"], d["grailQueryCost"]["totalCostDt"], d["runs"]["topWarningMessages"][:1])'
```

### 4. Draw conclusions
Ground them in the sources below, not in general intuition. State what is measured and what is inferred, and quote the
numbers.

## Background sources

**davis** (`analyzer-modules/davis.analyzer.module.rca.horizontal/`):
- `src/main/java/.../rca/TopologyCausalChainAnalyzer.java`: orchestration, `analysis_finished` / `events_fetched` logs.
- `src/main/java/.../rca/evidencedetector/novelty/NoveltyEvidenceDetector.java`: query + novelty detection + "ongoing" check.
- `src/main/java/.../rca/evidencedetector/novelty/BuiltinDqlTemplates.java`, `TimeseriesDqlQueryTemplate.java`: the DQL.
- `src/main/java/.../rca/evidencedetector/EvidenceDetectorRegistry.java`: born-closed handling.
- `src/main/resources/davis-analyzers/definitions/dt.rca.horizontal.TopologyCausalChainAnalyzer.json`: input defaults.
- `docs/research/novelty-detection.md`: novelty detector behaviour (step-up interval semantics, ongoing-check failure).

**CWS** (`loadtest-config/deus/rca/`):
- `README.md`, section "Novelty generators": exact metric shape and timing of the generated data.
- `novelty-pairs.pattern.yaml`, `novelty-hubs.pattern.yaml`: the patterns. They are edited between runs and only show
  the **last** used values. The size/mode of past runs comes from `runs.md`.

## Established facts (don't re-derive; re-check only if code or config changed)

TCCA behaviour under this series' config:
- Each execution issues 5 DQL queries: events snapshot, `smartscapeEdges` (every run, since cache is disabled), and one
  timeseries query each for request/messaging/faas **failure rate**. Root events are ERROR, so the latency detectors
  are configured but never run.
- Each detector sends **one** query per BFS depth containing **all** candidates of all root events
  (`iAny(dt.smartscape.service == toSmartscapeId(array(...)[]))`), with a 120 min lookback. There is no batching.
- Defaults in effect (not overridden by the payload): `minNoveltyScore 0.9`, `filterSpikes true`,
  `stillActiveToleranceMinutes 5`, `metricQueryLookbackMinutes 120`, RCA event TTL 5 min. The schedule is
  `FIXED_DELAY PT1M`, so the execution period is 60 s + analysis duration. Empty buckets in the duration series come
  from this, not from dropped executions.
- A novelty is **born closed** if its end is more than 5 min before `queryTo`. It is counted in `bfs_stats` but not
  attached, so it produces no PUP. `rcaEvents.open` = attached evidence.

CWS data:
- `I` = ingest start, floored to the minute. Root ERROR event `event.start = I-3`. Each callee has one series
  (`endpoint.name=/novelty`, 1000 req/min). `anomaly` steps from ~1 % to ~20 % failures at `I-3`; `baseline` stays at
  ~1 %; `none` writes no series. Fresh `SERVICE-…` ids per run, so runs cannot see each other's data.
- CWS expects the novelty to be ongoing for `queryTo ∈ [I-1, I+8]`. Open executions observed ≈ minutes from effective
  start to `I+8`.

Results so far (runs 1–12, see `summary.md`):
- Detect time and request query CPU scale with **candidates per query**, regardless of whether the candidates have data
  and regardless of the number of root events (hub ≈ pairs). The query hits the DQL request time limit (~10.35 s) between
  500 and 1000 candidates (extrapolated ~700). Above that, every execution fails with `Request time limit was
  exceeded…` and no evidence is produced.
- Grail CPU per query varies up to 2× between runs with identical setups, and CPU billed for timed-out queries is
  erratic. Don't attribute cost differences to the metric mode from single runs.
- Detection is exact for the synthetic step (one novelty per candidate per execution, none on baseline). Only ~25–30 %
  of executions produce open evidence because of the ongoing check.
