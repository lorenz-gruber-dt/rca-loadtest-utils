## Context

These loadtests were performed to see how novelty detection affects TCCA load. The input config (see ./tcca-task-payload.json) that was used for the TCCA analyzer mirrors the one that DAS would currently produce (as of 16.10.2026) based on the schema default current, but with 2 changes: all 6 anomaly detectors are active, caching is disabled.

The loadtest data was ingested by CWS with 2 patterns:

- service pairs
- hub

**Service pairs pattern**
Repeats a pair of two services n times. Each pair has one caller service with an error event. This error event is fetched by TCCA as a root event. This service calls a callee service with an failure rate metric (`dt.service.request.count / failure_count`).

**Service pairs hub**
1 "hub" service with n callee services. The hub service holds the root error event. Each callee has a failure rate metric.

There are 3 metric modes:

- anomaly
- baseline
- none

**Anomaly mode**
120 (2h, 1 points/minute) stable baseline metric points are ingested 2h into the past from the start of the ingestion period. At the start of the period the failure rate is raised and kept at that level for the rest of the run. This way TCCA finds an anomaly and is able to merge it with the root event.

**Baseline mode**
Also backfills a stable baseline 2h into the past, but never raises it. The same low baseline failure rate is kept for the entire run.

**None mode**
No metrics are ingested at all.

Each test lists a start/end time and an effective start/end time. The star/end times represent the timeframe where CWS actually ran. The effective start/end times reflect the timeframe where TCCA actually found and processed the ingested events. They differe due to ingest delay and event TTL.
For the purpose of analysing the results only the effective timeframe matters.

`gan7755d` was used as the target tenant for these tests.

---

## Test 1

**Date**: 15.10.2026
**Start time**: 16:03
**End time**: 16:23
**Effective start time**: 16:04
**Effective end time**: 16:28

**Pattern**: service pairs
**Pair count**: 100
**Metric mode**: anomaly

## Test 2

**Date**: 15.10.2026
**Start time**: 16:33
**End time**: 16:53
**Effective start time**: 16:35
**Effective end time**: 16:59

**Pattern**: service pairs
**Pair count**: 100
**Metric mode**: baseline

## Test 3

**Date**: 15.10.2026
**Start time**: 17:02
**End time**: 17:22
**Effective start time**: 17:05
**Effective end time**: 17:27

**Pattern**: service pairs
**Pair count**: 100
**Metric mode**: none

## Test 4

**Date**: 16.10.2026
**Start time**: 11:31
**End time**: 11:51
**Effective start time**: 11:34
**Effective end time**: 11:58

**Pattern**: service pairs
**Pair count**: 500
**Metric mode**: anomaly

## Test 5

**Date**: 16.10.2026
**Start time**: 12:27
**End time**: 12:42
**Effective start time**: 12:29
**Effective end time**: 12:53

**Pattern**: service pairs
**Pair count**: 500
**Metric mode**: baseline

## Test 6

**Date**: 16.10.2026
**Start time**: 12:57
**End time**: 13:12
**Effective start time**: 12:59
**Effective end time**: 13:23

**Pattern**: service pairs
**Pair count**: 500
**Metric mode**: none

## Test 7

**Date**: 16.10.2026
**Start time**: 13:26
**End time**: 13:41
**Effective start time**: 13:28
**Effective end time**: 13:52

**Pattern**: service pairs
**Pair count**: 1000
**Metric mode**: anomaly

## Test 8

**Date**: 16.10.2026
**Start time**: 13:59
**End time**: 14:14
**Effective start time**: 14:02
**Effective end time**: 14:25

**Pattern**: service pairs
**Pair count**: 1000
**Metric mode**: baseline

## Test 9

**Date**: 16.10.2026
**Start time**: 14:29
**End time**: 14:44
**Effective start time**: 14:31
**Effective end time**: 14:55

**Pattern**: service pairs
**Pair count**: 1000
**Metric mode**: none

## Test 10

**Date**: 16.10.2026
**Start time**: 15:03
**End time**: 15:18
**Effective start time**: 15:06
**Effective end time**: 15:30

**Pattern**: hub
**Pair count**: 100
**Metric mode**: anomaly

## Test 11

**Date**: 16.10.2026
**Start time**: 15:38
**End time**: 15:53
**Effective start time**: 15:40
**Effective end time**: 16:04

**Pattern**: hub
**Pair count**: 500
**Metric mode**: anomaly

## Test 12

**Date**: 16.10.2026
**Start time**: 16:16
**End time**: 16:31
**Effective start time**: 16:18
**Effective end time**: 16:43

**Pattern**: hub
**Pair count**: 1000
**Metric mode**: anomaly
