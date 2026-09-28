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
database. The default profiles are exactly 1,000 and 10,000 records. Select the
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
