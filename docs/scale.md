# Mixed signed-history measurement

Run the same real PostgreSQL/OPA harness used by the integration suite:

```sh
export CIO_TEST_DATABASE_URL=postgresql+pg8000://USER:PASSWORD@127.0.0.1:5432/postgres
export CIO_OPA=/absolute/path/to/opa
export CIO_SCALE_REPORT_DIR=.local/scale
uv run pytest tests/integration/test_scale.py -q
```

The database role must be able to create isolated test databases. Each profile
creates and drops its own random database; it does not populate the named admin
database. The default mixed-history profiles are exactly 1,000 and 10,000 records;
the work-discovery profiles add that many background work records to their fixed
target setup. Select the
stress profile with `CIO_SCALE_COUNTS=100000`, or all three with
`CIO_SCALE_COUNTS=1000,10000,100000`. PowerShell uses `$env:NAME='value'` for these
environment variables. CI saves the default JSON reports as `scale-observations`.

Every setup record is signed and verified before insertion through the Store's
normal internal projection writer, in batches of at most 100. Setup time is reported
separately from qualification. The target has one dependency and two independent
PASS records. Unrelated history includes capabilities, PASS/FAIL/UNKNOWN evidence,
withdrawals of that evidence, and verification events with explicitly unavailable
USD costs. Thus growing the dataset does not silently replace uncertainty with
zero cost or omit negative records. The final partial group makes the total exact.

After PostgreSQL ANALYZE, the harness performs five qualifications. Each must ACCEPT,
verify exactly four signatures, execute at most 16 DB statements and return at most
20 SELECT rows. These are regression bounds for this fixture, not general latency
or constant-complexity guarantees. Related evidence or deeper dependency graphs
require more work and still have their own safety limits. The report records actual
counts, not just the bounds. EXPLAIN ANALYZE with buffers captures every envelope
query from the final call, using the actual bound parameters.
The direct local-Store fixture establishes trusted-host source observations after
bulk insertion. Setting them before a long load caused the first 100,000-record
attempt to return UNKNOWN after the ordinary 300-second freshness window elapsed.
The production freshness limit is unchanged; persistent peer runtimes still obtain
observations only through completed synchronization.

Measurements distinguish:

- Total qualification latency with Python allocation tracing enabled.
- Time spent awaiting each real OPA subprocess call, including its launch and I/O.
- JSON bytes of verified DB envelopes, excluding DB framing and network protocol
  overhead. This is not an A2A bandwidth measurement.
- Peak Python traced allocations during each call, excluding PostgreSQL, OPA,
  native heaps and allocations retained before tracing. This is not total RSS.
- Python, PostgreSQL, OPA, operating system and CPU conditions.

Initial local 1,000/10,000 runs passed with four verified signatures, nine DB
statements and nine returned SELECT rows per call in both profiles. The 10,000-record
plans used subject indexes for capabilities/evidence and subject/withdrawal indexes
for revocations. This demonstrates bounded returned work for this fixture, not a
universal performance claim. Full observations and final stress results are recorded
in the validation status when the corresponding run completes.

OPA subprocess cost remains part of the measured path. This harness does not justify
introducing another service or a second implementation of the policy rules.

The revised run passed all three profiles in 673.69 seconds with migration 0008
installed. Raw observations, including all five repetitions and query plans:
[1,000](measurements/scale-1000.json), [10,000](measurements/scale-10000.json),
[100,000](measurements/scale-100000.json). The host was shared with development and
other test processes; latency is an observation under those conditions, not a
dedicated-machine benchmark. Every profile verified four signatures, executed nine
DB statements and returned nine SELECT rows for each target qualification.

## 0.3.0 work-history discovery profile

`test_work_history_discovery_scale` adds signed Opportunity, Proposal and local
Event v3 observations in bounded batches (at most 102 records). Half the generated
groups share the target subject; the rest use unrelated subjects. These are
synthetic history-volume records, not independently verified work or successful
business outputs. Proposal references pin their corresponding original signed
opportunity payloads. The active target is one registered goal with an actual
independent-evidence deficit, evaluated through the existing Registry, Store and
OPA paths. The profile does not introduce a separate discovery implementation.

Before loading history, the test measures deduplication and fresh discovery after
an explicit goal revision. After loading and ANALYZE, it measures another fresh
goal revision plus five sequential deduplications of the original unchanged cause.
The database statement count, returned SELECT row count, signature checks and OPA
call count must match their respective pre-load observations. Timings have no
pass/fail threshold. Actual envelope-query plans are retained with the raw reports.

Reports separate inclusive discovery latency, OPA subprocess time, signature
verification/signing time, DB cursor execution and Python traced allocations.
Cursor time excludes connection-pool waiting and result decoding. Component times
are diagnostic observations within the inclusive call, not additional charges.
CPU consumption, tokens and currency remain unavailable. Network collection,
selection, model inference and execution are not exercised by this profile; their
integration coverage must not be inferred from these discovery measurements.

The 0.3.1 profile uses distinct Goal IDs for the two fresh scenarios. The original
0.3.0 measurements below used revisions; under 0.3.1's stable owner/Goal cause
contract, changing that original Goal revision supersedes its older instance.
Distinct fresh Goal causes keep the unchanged original instance available for the
same bounded deduplication comparison. Historical measurements are retained.

Recorded on Windows/Python 3.12.10 with PostgreSQL 16.15 in WSL and OPA 1.21.0:

| Background records | Setup seconds | Fresh discovery seconds | Deduplication seconds, five calls |
| --- | --- | --- | --- |
| 1,000 | 4.560 | 0.116 | 0.090, 0.099, 0.097, 0.101, 0.101 |
| 10,000 | 47.023 | 0.157 | 0.141, 0.149, 0.164, 0.166, 0.105 |
| 100,000 | 437.109 | 0.152 | 0.113, 0.158, 0.163, 0.134, 0.134 |

All three saved profiles retain 12 DB statements, six returned rows, three signature
checks and one OPA call for deduplication; fresh discovery retains its 15-statement,
six-row baseline. Raw measurements include source hashes and actual plans:
[1k](measurements/work-scale-030-1000.json),
[10k](measurements/work-scale-030-10000.json),
[100k](measurements/work-scale-030-100000.json).
The 1k/10k focused run passed two tests in 57.08 seconds, zero skips. Both 100k
profiles saved their reports after their assertions completed; the mixed profile
also emitted a passing test marker. Its retained [mixed-history report](measurements/scale-030-100000.json)
shows four signature checks, nine statements and nine rows per qualification.
The combined stress process no longer exists after the interrupted session, and
its terminal footer/exit status was not retained. These reports establish completed
profile measurements, not a claim about that process's final exit status. Default
1k/10k source and distribution tests remain release gates. Latencies are observations
on this host, without an SLO or comparison of inference or distributed execution.
