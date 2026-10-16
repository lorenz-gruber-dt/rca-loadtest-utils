# TCCA novelty detection loadtests – results (runs 1–12)

Data: `run-NN.json`, produced by `rca_loadtest_summary.py --tenant gan7755d --context gmg80500` over the
**effective** timeframe of each run (local CEST times from `runs.md` converted to UTC, i.e. −2h).
Each run section links to the [\[TSG\]\[Obs\] RCA - Loadtest](https://gmg80500.dev.apps.dynatracelabs.com/ui/apps/dynatrace.dashboards/dashboard/a9eb4df8-1a86-409d-bd72-8363f96a5470)
dashboard with the tenant and timeframe prefilled.

Relevant config (`tcca-task-payload.json` + analyzer definition defaults, since the payload does not override them):

- schedule `FIXED_DELAY PT1M`, analysis window `now()-60m`, `maxTraversalDepth: 1`, `processingTimeLimitSeconds: 50`, cache disabled
- novelty detectors: `minNoveltyScore 0.9`, `filterSpikes true`, `metricQueryLookbackMinutes 120`, `stillActiveToleranceMinutes 5`
- RCA event TTL: 5 min (`CorrelatedRcaEvent.TTL_MINUTES`)
- Root events are `ERROR`, so only the `ERROR → ERROR` hop rule fires. That rule only references the 3 **failure rate**
  detectors (request / messaging / faas). The 3 latency detectors are configured but are **never executed** in these tests.
- Each detector issues **one** batched timeseries query per execution covering all candidate nodes
  (`filter: { iAny(dt.smartscape.service == toSmartscapeId(array(<all ids>)[])) }`), with a 120 min lookback.
  So every execution = 5 DQL queries: events snapshot, smartscapeEdges, and 3× timeseries.

Load data (CWS `loadtest-config/deus/rca/novelty-pairs.pattern.yaml` / `novelty-hubs.pattern.yaml`, see the `README.md` there):

- `I` = CWS ingest start, floored to the minute. Each caller gets one `ERROR_EVENT` with `event.start = I-3`; callees get no event.
- Each metric-writing callee has exactly **one** series (`endpoint.name = /novelty`, `dt.service.request.count` = 1000/min).
  `anomaly`: failure_count ≈ 10 (~1 %) backfilled for `I-120 … I-4`, then a hard step to ≈ 200 (~20 %) from `I-3` on,
  continued live every minute. `baseline`: ≈ 10 throughout (±3 jitter). `none`: no series at all.
- Every run uses fresh service names and therefore fresh `SERVICE-…` ids (run id embedded in the name), so runs
  cannot see each other's data.
- CWS's own expectation for `anomaly`: the novelty is ongoing for TCCA `queryTo` in `[I-1, I+8]`.

## Per-run summaries

| Run | Pattern / size / mode  | Execs | Warn % | Root ev./exec | PUPs (per exec) | RCA open / born-closed | Analysis avg / max (ms) | Detector avg (ms) | Request TS query CPU avg / max (s) | Total CPU (s) | Cost (DT$) | Extrap. DT$/yr |
|----:|------------------------|------:|-------:|--------------:|----------------:|-----------------------:|------------------------:|------------------:|-----------------------------------:|--------------:|-----------:|---------------:|
| 1 | pairs / 100 / anomaly  | 23 | 0   | 100  | 700 (30.4)   | 700 / 1600  | 2031 / 2595   | 1816  | 2.55 / 2.93   | 60.8  | 0.0024 | 53  |
| 2 | pairs / 100 / baseline | 23 | 0   | 100  | 0            | 0 / 0       | 2127 / 2300   | 1934  | 3.11 / 3.22   | 72.3  | 0.0029 | 63  |
| 3 | pairs / 100 / none     | 21 | 0   | 100  | 0            | 0 / 0       | 2264 / 2319   | 2071  | 3.27 / 3.33   | 69.3  | 0.0028 | 66  |
| 4 | pairs / 500 / anomaly  | 21 | 0   | 500  | 3000 (142.9) | 3000 / 7500 | 7580 / 8457   | 7253  | 13.61 / 13.89 | 287.5 | 0.0115 | 252 |
| 5 | pairs / 500 / baseline | 21 | 0   | 500  | 0            | 0 / 0       | 7697 / 8130   | 7429  | 7.24 / 7.42   | 154.7 | 0.0062 | 136 |
| 6 | pairs / 500 / none     | 21 | 0   | 500  | 0            | 0 / 0       | 6926 / 7316   | 6681  | 11.23 / 12.03 | 237.6 | 0.0095 | 208 |
| 7 | pairs / 1000 / anomaly | 20 | 100 | 1000 | **0**        | **0 / 0**   | 11328 / 11446 | 10361 | 20.52 / 20.57 | 411.9 | 0.0165 | 361 |
| 8 | pairs / 1000 / baseline| 19 | 100 | 1000 | 0            | 0 / 0       | 11499 / 11837 | 10373 | 20.63 / 20.73 | 408.9 | 0.0164 | 374 |
| 9 | pairs / 1000 / none    | 20 | 100 | 1000 | 0            | 0 / 0       | 11280 / 12034 | 10362 | 26.58 / 33.40 | 550.2 | 0.0220 | 482 |
| 10 | hub / 100 / anomaly   | 23 | 0   | 1    | 6 (0.26)     | 600 / 1700  | 2034 / 2197   | 1840  | 3.12 / 3.64   | 72.7  | 0.0029 | 64  |
| 11 | hub / 500 / anomaly   | 21 | 0   | 1    | 5 (0.24)     | 2500 / 8000 | 6882 / 7131   | 6688  | 12.84 / 15.28 | 270.4 | 0.0108 | 237 |
| 12 | hub / 1000 / anomaly  | 20 | 100 | 1    | **0**        | **0 / 0**   | 10545 / 10577 | 10353 | 22.75 / 25.88 | 455.6 | 0.0182 | 383 |

Size = number of pairs (pairs pattern) or number of callees of the single hub caller (hub pattern). Either way it is the
number of depth-1 candidates per detector.

All runs: the request failure rate timeseries query accounts for 94.7–99.9 % of total Grail CPU. Messaging and faas
queries are effectively free (≤ 0.2 s CPU over a whole run). Event fetches take ~105–190 ms. smartscapeEdges is
0.3–5 % of CPU.

### Run 1 – 100 pairs, anomaly
[Dashboard](https://gmg80500.dev.apps.dynatracelabs.com/ui/apps/dynatrace.dashboards/dashboard/a9eb4df8-1a86-409d-bd72-8363f96a5470#from=2026-10-15T14%3A04%3A00.000Z&to=2026-10-15T14%3A28%3A00.000Z&vfilter_Tenant=gan7755d) · `2026-10-15T14:04:00Z` – `2026-10-15T14:28:00Z`

Every execution found all 100 root events. Novelty detection produced exactly **one RCA event per pair per execution**
(2300 = 23 × 100), but only 700 of them (= 7 executions' worth) were still "ongoing". The other 1600 were born closed and
did not produce a PUP. Analysis ~2 s, of which ~90 % is the detect stage. Request query CPU grew steadily from 2.1 s to
2.9 s over the run.

### Run 2 – 100 pairs, baseline
[Dashboard](https://gmg80500.dev.apps.dynatracelabs.com/ui/apps/dynatrace.dashboards/dashboard/a9eb4df8-1a86-409d-bd72-8363f96a5470#from=2026-10-15T14%3A35%3A00.000Z&to=2026-10-15T14%3A59%3A00.000Z&vfilter_Tenant=gan7755d) · `2026-10-15T14:35:00Z` – `2026-10-15T14:59:00Z`

No novelties at all: 0 RCA events, 0 born-closed, 0 PUPs, so no false positives on the stable baseline. Cost and
duration are the same as or slightly higher than run 1 (3.1 s vs 2.55 s request query CPU).

### Run 3 – 100 pairs, none
[Dashboard](https://gmg80500.dev.apps.dynatracelabs.com/ui/apps/dynatrace.dashboards/dashboard/a9eb4df8-1a86-409d-bd72-8363f96a5470#from=2026-10-15T15%3A05%3A00.000Z&to=2026-10-15T15%3A27%3A00.000Z&vfilter_Tenant=gan7755d) · `2026-10-15T15:05:00Z` – `2026-10-15T15:27:00Z`

Same as run 2: nothing detected. Request query CPU (3.27 s) is the **highest** of the 100-pair runs, even though no
metrics were ingested for the candidate services.

### Run 4 – 500 pairs, anomaly
[Dashboard](https://gmg80500.dev.apps.dynatracelabs.com/ui/apps/dynatrace.dashboards/dashboard/a9eb4df8-1a86-409d-bd72-8363f96a5470#from=2026-10-16T09%3A34%3A00.000Z&to=2026-10-16T09%3A58%3A00.000Z&vfilter_Tenant=gan7755d) · `2026-10-16T09:34:00Z` – `2026-10-16T09:58:00Z`

All 500 root events fetched every execution. One RCA event per pair per execution (10500 = 21 × 500), 3000 open
(= 6 executions' worth) and 7500 born closed. Analysis ~7.6 s. Request query ~13.6 s CPU per execution, flat over the run.

### Run 5 – 500 pairs, baseline
[Dashboard](https://gmg80500.dev.apps.dynatracelabs.com/ui/apps/dynatrace.dashboards/dashboard/a9eb4df8-1a86-409d-bd72-8363f96a5470#from=2026-10-16T10%3A29%3A00.000Z&to=2026-10-16T10%3A53%3A00.000Z&vfilter_Tenant=gan7755d) · `2026-10-16T10:29:00Z` – `2026-10-16T10:53:00Z`

Nothing detected. Wall-clock duration matches run 4 (~7.4 s detect), but request query CPU is only about half
(7.2 s vs 13.6 s).

### Run 6 – 500 pairs, none
[Dashboard](https://gmg80500.dev.apps.dynatracelabs.com/ui/apps/dynatrace.dashboards/dashboard/a9eb4df8-1a86-409d-bd72-8363f96a5470#from=2026-10-16T10%3A59%3A00.000Z&to=2026-10-16T11%3A23%3A00.000Z&vfilter_Tenant=gan7755d) · `2026-10-16T10:59:00Z` – `2026-10-16T11:23:00Z`

Nothing detected. Request query CPU 11.2 s, rising from 9.5 s to 12.0 s over the run. Wall-clock duration is again ~7 s.

### Run 7 – 1000 pairs, anomaly
[Dashboard](https://gmg80500.dev.apps.dynatracelabs.com/ui/apps/dynatrace.dashboards/dashboard/a9eb4df8-1a86-409d-bd72-8363f96a5470#from=2026-10-16T11%3A28%3A00.000Z&to=2026-10-16T11%3A52%3A00.000Z&vfilter_Tenant=gan7755d) · `2026-10-16T11:28:00Z` – `2026-10-16T11:52:00Z`

**Every execution failed the request failure rate query**:
`Request time limit was exceeded for DQL result. Please try to narrow down the query.` (20/20 executions →
`SUCCESSFUL_WITH_WARNINGS`). The detect stage is pinned at ~10.35 s, which is the DQL request time limit, not TCCA's 50 s
budget. Even though a real anomaly was present and all 1000 root events were fetched, TCCA produced **0 RCA events and
0 PUPs**. The timed-out queries were still billed at ~20.5 s CPU each.

### Run 8 – 1000 pairs, baseline
[Dashboard](https://gmg80500.dev.apps.dynatracelabs.com/ui/apps/dynatrace.dashboards/dashboard/a9eb4df8-1a86-409d-bd72-8363f96a5470#from=2026-10-16T12%3A02%3A00.000Z&to=2026-10-16T12%3A25%3A00.000Z&vfilter_Tenant=gan7755d) · `2026-10-16T12:02:00Z` – `2026-10-16T12:25:00Z`

Same failure as run 7 (19/19 executions). Nothing could have been detected anyway. ~20.6 s CPU billed per failed query.

### Run 9 – 1000 pairs, none
[Dashboard](https://gmg80500.dev.apps.dynatracelabs.com/ui/apps/dynatrace.dashboards/dashboard/a9eb4df8-1a86-409d-bd72-8363f96a5470#from=2026-10-16T12%3A31%3A00.000Z&to=2026-10-16T12%3A55%3A00.000Z&vfilter_Tenant=gan7755d) · `2026-10-16T12:31:00Z` – `2026-10-16T12:55:00Z`

Same failure (20/20). Billed CPU per failed query climbs from 20.4 s to 29–33 s during the run.

### Run 10 – hub, 100 callees, anomaly
[Dashboard](https://gmg80500.dev.apps.dynatracelabs.com/ui/apps/dynatrace.dashboards/dashboard/a9eb4df8-1a86-409d-bd72-8363f96a5470#from=2026-10-16T13%3A06%3A00.000Z&to=2026-10-16T13%3A30%3A00.000Z&vfilter_Tenant=gan7755d) · `2026-10-16T13:06:00Z` – `2026-10-16T13:30:00Z`

One root event (the hub caller) and 100 candidates. Novelty detection again produced exactly one RCA event per callee per
execution (2300 = 23 × 100): 600 open (= 6 executions' worth) and 1700 born closed. Each of those 6 executions produced
**one** PUP carrying all 100 pieces of evidence, hence only 6 PUPs. Duration (2.0 s) and request query CPU (3.1 s) are the
same as the 100-pair runs, despite 1 root event instead of 100.

### Run 11 – hub, 500 callees, anomaly
[Dashboard](https://gmg80500.dev.apps.dynatracelabs.com/ui/apps/dynatrace.dashboards/dashboard/a9eb4df8-1a86-409d-bd72-8363f96a5470#from=2026-10-16T13%3A40%3A00.000Z&to=2026-10-16T14%3A04%3A00.000Z&vfilter_Tenant=gan7755d) · `2026-10-16T13:40:00Z` – `2026-10-16T14:04:00Z`

10500 = 21 × 500 RCA events: 2500 open (= 5 executions' worth, 5 PUPs with 500 pieces of evidence each) and 8000 born
closed. No warnings; the 500-evidence PUPs were emitted without problems. Analysis 6.9 s and request query 12.8 s CPU, in
the range of the 500-pair runs (6.9–7.7 s, 7.2–13.6 s). The first query of the run cost 15.3 s, the rest a flat ~12.7 s.

### Run 12 – hub, 1000 callees, anomaly
[Dashboard](https://gmg80500.dev.apps.dynatracelabs.com/ui/apps/dynatrace.dashboards/dashboard/a9eb4df8-1a86-409d-bd72-8363f96a5470#from=2026-10-16T14%3A18%3A00.000Z&to=2026-10-16T14%3A43%3A00.000Z&vfilter_Tenant=gan7755d) · `2026-10-16T14:18:00Z` – `2026-10-16T14:43:00Z`

Same failure as runs 7–9: the request failure rate query hit the DQL request time limit in 20/20 executions (detect
stage pinned at ~10.35 s). **0 RCA events, 0 PUPs**, even though there is just a single problem. Billed CPU per failed query
was ~25.8 s for the first 15 executions, then dropped to ~15.8 s and finally ~10.3 s. All 20 executions still found the
root event, so this is not explained by the test data changing; it shows again that billed CPU of a timed-out query is
not stable.

## Comparison and conclusions

### 1. Novelty detection hits a hard cliff between 500 and 1000 candidates
Detect-stage wall time scales roughly linearly: ~1.9 s at 100 candidates, ~7.1 s at 500 (≈ 13 ms per candidate plus ~0.6 s
fixed). That extrapolates to the ~10 s DQL request time limit at **~700 candidate nodes per detector**. Above that, the
single batched request query times out on every execution, and novelty-based evidence disappears entirely (run 7: real
anomaly, 0 PUPs). The hub pattern reproduces the cliff at the same point (run 12: 1000 callees of a single root event,
20/20 timeouts, 0 PUPs), so the limit is set by the number of candidates per query and nothing else. The failure only shows up as a warning. The analyzer still reports success, fetches all root events, and
pays full CPU for queries that return nothing.

Since there is one query per detector per execution with all candidates in the filter, the number of candidates scales
with the size of the problem landscape, not with anything configurable. Chunking the candidate set (e.g. ≤ 300–400 ids
per query, possibly in parallel) would keep each query below the limit. A cap with an explicit warning would at least
make the degradation visible.

### 2. Pairs vs hub: candidate count is all that matters, root event count is irrelevant
| Candidates | Pattern | Root events | Detect avg (ms) | Request query CPU avg (s) | Events fetch (ms) | RCA events | PUPs |
|-----------:|---------|------------:|----------------:|--------------------------:|------------------:|-----------:|-----:|
| 100  | pairs (run 1) | 100  | 1816 | 2.55 (2.55–3.27 over runs 1–3) | 106 | 2300  | 700  |
| 100  | hub (run 10)  | 1    | 1840 | 3.12                           | 111 | 2300  | 6    |
| 500  | pairs (run 4) | 500  | 7253 | 13.61 (7.24–13.61 over runs 4–6) | 189 | 10500 | 3000 |
| 500  | hub (run 11)  | 1    | 6688 | 12.84                          | 103 | 10500 | 5    |
| 1000 | pairs (run 7) | 1000 | 10361 (timeout) | 20.52 (failed)      | 159 | 0     | 0    |
| 1000 | hub (run 12)  | 1    | 10353 (timeout) | 22.75 (failed)      | 100 | 0     | 0    |

With the same number of candidates, a hub with one root event and N pairs with N root events behave identically:
same duration, same CPU within the run-to-run noise from point 6, the same timeout at 1000, and the same number of RCA
events. The root-event side (event fetch ~100–190 ms, smartscapeEdges ≤ 5 % of CPU, lower for the hub) is negligible
either way.

Consequences:

- **The limit is tenant-wide, not per problem.** TCCA puts all new candidates of all root events of an execution into one
  query per detector and depth. 1000 unrelated small problems (pairs) and one large fan-out problem (hub) hit the same
  wall. In a real tenant, a single gateway/frontend error event with ~1000 downstream services would therefore not
  only lose its own evidence. It would also break novelty evidence for **every other active problem** in that tenant for as
  long as it stays a root event.
- Hub-like fan-out is common in production (frontends, API gateways, shared backends). These tests use
  `maxTraversalDepth: 1`, while the analyzer default is 2, where depth-2 candidates get their own query per detector. That
  adds a second query that can independently cross the limit.
- **PUP count is not a load indicator.** The hub runs produced 6 and 5 PUPs against 700 and 3000 for the same work, because
  one PUP carries all evidence of its problem. A single PUP with 500 pieces of evidence (run 11) was emitted without
  warnings. Candidate count, or RCA events including born-closed ones, is the metric to watch for TCCA load.

### 3. Query cost does not depend on whether the candidates have data
At every scale, the `none` runs cost as much as or more than the `anomaly`/`baseline` runs (100: 3.27 s vs 2.55/3.11 s;
500: 11.2 s vs 13.6/7.2 s; 1000: all timed out). In `none` mode the query matches **zero** series. In the other modes it
returns at most N series × 120 points, which is tiny. So the cost is not in reading or returning the candidates' data. It
scales with the number of ids in the `iAny(... array(N ids))` entity filter: ~15–33 ms CPU per candidate per execution
(≈ 0.3–0.7 DT$/yr per continuously-monitored candidate at 1 exec/min).

What else drives it is unclear. Messaging and faas queries, with the same filter size but on metrics this tenant barely
has, are essentially free, which points at the tenant's `dt.service.request.*` series population. But that doesn't line
up run by run. Run 5's 120 min lookback also contains run 4's 500 series, so it covers twice as many series as run 4,
yet it cost half as much. A clean single-variable test (same N, repeated, with and without background series) would be
needed to separate filter size from tenant cardinality. Until then, production tenants with far more request series
should be assumed to be at least as expensive per candidate as this one.

The query also re-reads the full 120 min lookback every minute, so ~119/120 of the scanned data is identical to the
previous execution. Incremental or cached timeseries would be the larger saving if this needs to get cheaper.

### 4. Detection itself is reliable: one novelty per series, no false positives
In all four anomaly runs that could query (1, 4, 10, 11), every candidate yielded exactly one RCA event per execution, with no misses
and no duplicates (multiple novelties per series would have pushed the total above `execs × candidates`). Both baseline runs
produced zero novelties, including zero born-closed ones. With `minNoveltyScore 0.9` and `filterSpikes true`, the
noise-suppression recommendations from the research doc are in effect and behave as intended.

Caveat: a synthetic, perfectly flat baseline is the easiest possible case. The research doc shows real request failure
rates produce many low-score spikes and trends, so these runs say little about the production false-positive rate.

### 5. The "ongoing" check limits evidence to a short window after onset
Only 24–30 % of executions produced an open RCA event per candidate (run 1: 7/23, run 4: 6/21, run 10: 6/23,
run 11: 5/21). All others were born
closed, even though the failure rate stayed elevated for the whole run. This matches the step-up behaviour described in
the research doc (*Novelty Interval Semantics*). The change-point novelty interval settles at roughly `t1 + buf` once the
new level is established. After that, `noveltyEnd` falls out of `stillActiveToleranceMinutes` (5 min) and the novelty
counts as ended, although the anomaly is still ongoing. Born-closed detections are deliberately not attached to the graph
(`EvidenceDetectorRegistry`), so no PUP is produced for them.

The counts match the CWS design exactly. CWS expects the novelty to be ongoing for `queryTo ∈ [I-1, I+8]`, i.e. until
~11 min after the step at `I-3`. TCCA can only use the part of that window after the root events become visible, which
is the effective start:

| Run | CWS start (`I`) | Effective start | Usable ongoing window | Expected open execs (~62–67 s period) | Observed |
|----:|----------------:|----------------:|----------------------:|--------------------------------------:|---------:|
| 1 | 16:03 | 16:04 (`I+1`) | `I+1 … I+8` ≈ 8 min | ~7–8 | **7** |
| 4 | 11:31 | 11:34 (`I+3`) | `I+3 … I+8` ≈ 6 min | ~5–6 | **6** |
| 10 | 15:03 | 15:06 (`I+3`) | `I+3 … I+8` ≈ 6 min | ~5–6 | **6** |
| 11 | 15:38 | 15:40 (`I+2`) | `I+2 … I+8` ≈ 7 min | ~6 | **5** |

Run 11 is one execution short. The effective start times are only minute-precise, so a ±1 deviation is within what this
comparison can resolve.

Consequences:

- Evidence exists for only ~5–7 of the 15–20 minutes the failure rate stays elevated. With the 5 min RCA event TTL, the
  evidence event lapses around `I+13`, while the root ERROR event and the anomaly continue until CWS stops.
- **Root event visibility delay is subtracted 1:1 from the evidence window.** Here, a 1–3 min ingest delay cost 1–3
  executions. In production, a Davis ERROR event is raised some time after the metric degrades (baselining needs
  several violating minutes). If the root event appears more than ~`buf + stillActiveTolerance` (~11 min here) after the
  callee's change point, TCCA reports **no evidence at all**. This is the "Ongoing Novelty Check Failure" scenario from the
  research doc, and these runs show how small the margin is even for an ideal step.
- The open detections should cluster right after the anomaly onset, which per-execution logs or the dashboard can
  confirm. The design question is whether "ongoing" should mean "level still elevated" rather than "transition still
  recent".
- Born-closed detections cost exactly as much to compute as open ones: in run 4, ~70 % of the detect work produced no
  output.

### 6. Duration, CPU cost, and cost variance
- Wall-clock duration is very stable across modes at the same scale (500: 6.7–7.4 s detect for all three modes), but
  CPU per query varied almost 2× (7.2 s vs 13.6 s). CPU-based cost comparisons between single runs are noisy, so repeat
  runs would be needed before attributing cost differences to the metric mode.
- Request query CPU drifted upwards within several runs (run 1: 2.1→2.9 s, run 6: 9.5→12.0 s, run 9: 20.4→33.4 s).
  For timed-out queries, CPU kept growing even though the client gave up at ~10 s. Run 12 went the other way
  (25.8 → 15.8 → 10.3 s per failed query in its last 5 executions, with unchanged input). Billed cost for failed queries is
  therefore not bounded by the timeout, and the 1000-pair figures are a lower bound on what a successful query would cost.
- Executions per run (23 → 21 → 20 for 100 → 500 → 1000 candidates, identical for pairs and hub) drop because the schedule is `FIXED_DELAY`: the period is
  60 s + analysis duration. The periodic empty buckets in the duration timeseries are this effect, not dropped executions.

### 7. Coverage gaps in this test series
- The latency detectors (`*_latency_p50`, percentile aggregations, likely more expensive than the failure rate sums) were
  never exercised, because no SLOWDOWN root events were ingested. "All 6 detectors active" effectively tested 3.
- Only `maxTraversalDepth: 1` was tested, and the hub pattern only in `anomaly` mode. The cliff between 500 and 1000 is
  bracketed but not pinned down. A run at ~700–800 candidates would confirm the extrapolated limit, and a mixed
  test (one large hub plus small pairs in the same tenant) would directly show the tenant-wide blast radius from point 2.
- The anomaly is an ideal step: one series per callee, constant 1000 req/min, and the step already lies in the
  backfill (`I-3`) when TCCA first looks. TCCA never sees the change point form live, and there are no gradual ramps,
  low-traffic endpoints, or multiple endpoints per service. Real data would exercise the change-point establishing
  period and the per-endpoint series fan-out (the query splits `by: endpoint.name`), which this test doesn't.
