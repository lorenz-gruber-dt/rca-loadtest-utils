#!/usr/bin/env python3
"""Summarize an RCA loadtest for one tenant and one timeframe as JSON.

Mirrors the DQL of the "[TSG][Obs] RCA - Loadtest" dashboard. Uses only the
Python standard library and the `dtctl` CLI (current context must be the
tenant that holds the Davis analyzer execution logs and DQL query logs).

Usage:
  ./rca_loadtest_summary.py --tenant gan7755d --timeframe 2h
  ./rca_loadtest_summary.py --tenant gan7755d --timeframe 2026-10-16T10:00:00Z/2026-10-16T12:00:00Z

--timeframe: a relative window ending now (e.g. 30m, 2h, 7d, 1w) or START/END in ISO 8601.
Progress and errors go to stderr; the JSON result is the only thing on stdout.
"""
import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

COST_PER_CPU_SECOND = 0.00004  # DT$ — same fixed rate as the dashboard
UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}

# Davis analyzer execution logs (one JSON log line per analyzer run).
EXEC_PRE = """fetch logs, scanLimitGBytes:-1
| filter dt.system.bucket == "custom_sen_low_davis_analyzer_executions"
| filter k8s.namespace.name == "davis"
| filter contains(content, "ExecutionTrackingLogger")
| filter contains(content, "dt.rca.horizontal")
| filter contains(content, "{tenant}")
| parse content, "LD JSON:p"
| filter startsWith(p[`analyzer.name`], "dt.rca.horizontal.")
| filter p[`tenant`] == "{tenant}\""""


def info(log):
    """Expand the nested analyzer info messages of one log type into `d`."""
    return EXEC_PRE + f"""
| expand m = p[`analyzer.info_messages`]
| filter contains(m, "\\"log\\":\\"{log}\\"")
| parse m, "JSON:d\""""


QUERIES = {
    "runs": EXEC_PRE + """
| filter isNotNull(p[`analyzer.result_status`])
| summarize runs = count(), withWarnings = countIf(p[`analyzer.result_status`] == "SUCCESSFUL_WITH_WARNINGS")""",
    "warnings": EXEC_PRE + """
| expand msg = p[`analyzer.warning_messages`]
| parse msg, "JSON:d"
| fieldsAdd message = coalesce(d[`message`], d[`log`], msg)
| filter isNotNull(message) and message != ""
| summarize count = count(), by: { message }
| sort count desc
| limit 10""",
    "analysis": info("analysis_finished") + """
| summarize n = count(), pups = sum(toLong(d[`pups`])), rcaEvents = sum(toLong(d[`rcaEvents`])),
    avgMs = avg(toDouble(d[`durationMs`])), maxMs = max(toDouble(d[`durationMs`]))""",
    "bfs": info("bfs_stats") + """
| fieldsAdd hop = d[`depths`][][`hopStep`][`detect`][`durationMs`], same = d[`depths`][][`sameNodeStep`][`detect`][`durationMs`]
| fieldsAdd hopL = toLong(hop[]), sameL = toLong(same[])
| fieldsAdd detectMs = arraySum(hopL) + arraySum(sameL)
| summarize n = count(), bornClosed = sum(toLong(d[`bornClosedRcaEvents`])),
    avgMs = avg(toDouble(detectMs)), maxMs = max(toDouble(detectMs))""",
    "fetched": info("events_fetched") + """
| summarize n = count(), events = sum(toLong(d[`events`])),
    avgMs = avg(toDouble(d[`durationMs`])), maxMs = max(toDouble(d[`durationMs`]))""",
    # Time series (makeTimeseries; `interval` is filled in at runtime)
    "analysisSeries": info("analysis_finished") + """
| makeTimeseries { avgMs = avg(toDouble(d[`durationMs`])), maxMs = max(toDouble(d[`durationMs`])) }, interval: {interval}s""",
    "detectorSeries": info("bfs_stats") + """
| fieldsAdd hop = d[`depths`][][`hopStep`][`detect`][`durationMs`], same = d[`depths`][][`sameNodeStep`][`detect`][`durationMs`]
| fieldsAdd hopL = toLong(hop[]), sameL = toLong(same[])
| fieldsAdd detectMs = arraySum(hopL) + arraySum(sameL)
| makeTimeseries { avgMs = avg(toDouble(detectMs)), maxMs = max(toDouble(detectMs)) }, interval: {interval}s""",
    # One record per timeseries request query, chronological
    "requestCpu": """fetch logs, scanLimitGBytes:-1
| filter matchesPhrase(content, "DqlQueryLog") and matchesPhrase(content, "ALERTING") and matchesPhrase(content, "dt.rca.horizontal")
| filter matchesPhrase(content, "timeseries")
| filter tenant == "{tenant}"
| parse content, "LD 'JSON:' JSON:query"
| fieldsAdd cpuNanos = toDouble(query[tasks.be.times][real_ns]) + toDouble(query[tasks.fe.times][cpu_ns])
| filterOut isNull(cpuNanos)
| fieldsAdd dqlTokens = splitString(trim(replaceString(query[dql], "\\n", " ")), " ")
| filter dqlTokens[0] == "timeseries"
| filter contains(query[dql], "dt.service.request.")
| fields timestamp, cpuNanos
| sort timestamp asc""",
    # One row per (queryType, tsKind) over all DQL queries issued by the analyzers.
    "cost": """fetch logs, scanLimitGBytes:-1
| filter matchesPhrase(content, "DqlQueryLog")
| filter matchesPhrase(content, "ALERTING")
| filter matchesPhrase(content, "dt.rca.horizontal")
| filter tenant == "{tenant}"
| parse content, "LD 'JSON:' JSON:query"
| fieldsAdd cpuNanos = toDouble(query[tasks.be.times][real_ns]) + toDouble(query[tasks.fe.times][cpu_ns])
| filterOut isNull(cpuNanos)
| fieldsAdd dqlTokens = splitString(trim(replaceString(query[dql], "\\n", " ")), " ")
| fieldsAdd queryType = if(dqlTokens[0] == "fetch", concat("fetch ", replaceString(toString(dqlTokens[1]), ",", "")), else: toString(dqlTokens[0]))
| fieldsAdd tsKind = if(dqlTokens[0] != "timeseries", "", else: if(contains(query[dql], "dt.service.request."), "request", else: if(contains(query[dql], "dt.service.faas_invoke."), "faas", else: if(contains(query[dql], "dt.service.messaging.process."), "messaging", else: "other"))))
| summarize n = count(), sumNanos = sum(cpuNanos), maxNanos = max(cpuNanos), by: { queryType, tsKind }""",
}


def parse_timeframe(tf):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    m = re.fullmatch(r"(\d+)([smhdw])", tf)
    if m:
        return now - timedelta(seconds=int(m[1]) * UNITS[m[2]]), now
    if "/" in tf:
        a, b = tf.split("/", 1)
        try:
            parse = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
            start, end = parse(a), parse(b)
        except ValueError:
            sys.exit(f"invalid ISO 8601 timeframe: {tf!r}")
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if end <= start:
            sys.exit("timeframe end must be after start")
        return start, end
    sys.exit(f"invalid timeframe {tf!r}: use e.g. 2h, 30m, 7d or START/END in ISO 8601")


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_query(name, dql, start, end, extra):
    cmd = ["dtctl", *extra, "query", dql, "-o", "json", "--plain", "--max-result-records", "1000000",
           "--default-timeframe-start", iso(start), "--default-timeframe-end", iso(end)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"query '{name}' failed:\n{p.stderr.strip() or p.stdout.strip()}")
    out = p.stdout
    try:
        return json.loads(out[out.index("{"):])["records"]
    except (ValueError, KeyError):
        sys.exit(f"query '{name}': unexpected dtctl output:\n{out[:500]}")


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def rnd(v, d=2):
    return None if v is None else round(v, d)


def first(rows):
    return rows[0] if rows else {}


def duration_stats(row):
    has = num(row.get("n")) > 0
    return {"avgMs": rnd(num(row.get("avgMs")), 1) if has else None,
            "maxMs": rnd(num(row.get("maxMs")), 1) if has else None}


def pct(part, whole):
    return rnd(100.0 * part / whole, 2) if whole else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tenant", required=True, help="tenant id of the RCA loadtest, e.g. gan7755d")
    ap.add_argument("--timeframe", required=True, help="2h | 30m | 7d | START/END (ISO 8601)")
    ap.add_argument("--context", help="dtctl context to run against (default: current context)")
    args = ap.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", args.tenant):
        sys.exit("invalid tenant: only letters, digits, '_', '.', '-' are allowed")
    start, end = parse_timeframe(args.timeframe)
    seconds = (end - start).total_seconds()
    minutes = seconds / 60
    interval = max(60, int(round(seconds / 60 / 60)) * 60)  # ~60 buckets, whole minutes
    extra = ["--context", args.context] if args.context else []

    print(f"Querying {len(QUERIES)} datasets for tenant {args.tenant}, {iso(start)} .. {iso(end)}", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=len(QUERIES)) as ex:
        futs = {n: ex.submit(run_query, n, q.replace("{tenant}", args.tenant).replace("{interval}", str(interval)), start, end, extra)
                for n, q in QUERIES.items()}
        r = {n: f.result() for n, f in futs.items()}

    runs = first(r["runs"])
    n_runs = int(num(runs.get("runs")))
    n_warn = int(num(runs.get("withWarnings")))
    ana, bfs, fet = first(r["analysis"]), first(r["bfs"]), first(r["fetched"])

    pups = int(num(ana.get("pups")))
    open_events = int(num(ana.get("rcaEvents")))
    born_closed = int(num(bfs.get("bornClosed")))
    created = open_events + born_closed
    root_events = int(num(fet.get("events")))
    n_ana, n_fet = int(num(ana.get("n"))), int(num(fet.get("n")))

    # --- Grail query cost / CPU time
    cost = [{"type": x.get("queryType"), "kind": x.get("tsKind") or "", "n": num(x.get("n")),
             "sum": num(x.get("sumNanos")), "max": num(x.get("maxNanos"))} for x in r["cost"]]
    total_nanos = sum(c["sum"] for c in cost)
    total_queries = int(sum(c["n"] for c in cost))
    total_cpu_s = total_nanos / 1e9

    def by_type(pred):
        return sum(c["sum"] for c in cost if pred(c["type"]))

    def ts_stats(kind):
        rows = [c for c in cost if c["type"] == "timeseries" and c["kind"] == kind]
        n, s = sum(c["n"] for c in rows), sum(c["sum"] for c in rows)
        return {"queries": int(n), "totalCpuSeconds": rnd(s / 1e9, 3),
                "avgCpuSeconds": rnd(s / n / 1e9, 4) if n else None,
                "maxCpuSeconds": rnd(max(c["max"] for c in rows) / 1e9, 4) if rows else None}

    ts_total = sum(c["sum"] for c in cost if c["type"] == "timeseries")
    ts_kinds = {k: ts_stats(k) for k in ("request", "faas", "messaging")}
    for k, label in (("request", "request"), ("faas", "faas"), ("messaging", "messaging")):
        ts_kinds[k]["shareOfTimeseriesCpuPct"] = pct(sum(c["sum"] for c in cost if c["type"] == "timeseries" and c["kind"] == label), ts_total)
        ts_kinds[k]["shareOfTotalCpuPct"] = pct(sum(c["sum"] for c in cost if c["type"] == "timeseries" and c["kind"] == label), total_nanos)

    cost_dt = total_cpu_s * COST_PER_CPU_SECOND
    result = {
        "tenant": args.tenant,
        "timeframe": {"from": iso(start), "to": iso(end), "seconds": int(seconds)},
        "pups": {"total": pups,
                 "avgPerRun": rnd(pups / n_ana, 2) if n_ana else None,
                 "avgPerMinute": rnd(pups / minutes, 2)},
        "rcaEvents": {"total": created, "open": open_events, "bornClosed": born_closed,
                      "avgPerRun": rnd(created / n_ana, 2) if n_ana else None,
                      "avgPerMinute": rnd(created / minutes, 2),
                      "bornClosedPct": pct(born_closed, created)},
        "rootEventsFetched": {"total": root_events,
                              "avgPerRun": rnd(root_events / n_fet, 2) if n_fet else None,
                              "avgPerMinute": rnd(root_events / minutes, 2)},
        "runs": {"total": n_runs, "withWarnings": n_warn, "withWarningsPct": pct(n_warn, n_runs),
                 "topWarningMessages": [{"message": w.get("message"), "count": int(num(w.get("count")))}
                                        for w in r["warnings"]]},
        "durations": {"analysis": duration_stats(ana),
                      "eventsFetch": duration_stats(fet),
                      "detector": duration_stats(bfs)},
        "grailQueryCost": {
            "queries": total_queries,
            "totalCostDt": rnd(cost_dt, 6),
            "extrapolatedCostDtPerYear": rnd(cost_dt / seconds * 86400 * 365, 2),
            "costRateDtPerCpuSecond": COST_PER_CPU_SECOND,
            "sharePctOfCost": {
                "eventsSnapshots": pct(by_type(lambda t: t == "fetch dt.davis.events.snapshots"), total_nanos),
                "smartscapeEdges": pct(by_type(lambda t: t == "smartscapeEdges"), total_nanos),
                "timeseries": pct(ts_total, total_nanos),
                "other": pct(by_type(lambda t: t not in ("fetch dt.davis.events.snapshots", "smartscapeEdges", "timeseries")), total_nanos),
            },
            "sharePctByQueryType": {t: pct(by_type(lambda x, t=t: x == t), total_nanos)
                                    for t in sorted({c["type"] for c in cost}, key=lambda t: -by_type(lambda x: x == t))},
        },
        "grailCpuTime": {
            "totalSeconds": rnd(total_cpu_s, 3),
            "requestQueries": ts_kinds["request"],
            "faasQueries": ts_kinds["faas"],
            "messagingProcessQueries": ts_kinds["messaging"],
            "sharePctOfTotalCpu": {k: ts_kinds[k]["shareOfTotalCpuPct"] for k in ts_kinds},
        },
    }
    def series(rows, key):
        row = first(rows)
        vals = row.get(key) or []
        return [None if v is None else rnd(num(v), 1) for v in vals]

    result["timeseries"] = {
        "intervalSeconds": interval,
        "from": iso(start),
        "analysisDurationMs": {"avg": series(r["analysisSeries"], "avgMs"), "max": series(r["analysisSeries"], "maxMs")},
        "detectorDurationMs": {"avg": series(r["detectorSeries"], "avgMs"), "max": series(r["detectorSeries"], "maxMs")},
        # one value per request query, chronological
        "requestQueryCpuSeconds": [rnd(num(x.get("cpuNanos")) / 1e9, 4) for x in r["requestCpu"]],
    }
    json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
