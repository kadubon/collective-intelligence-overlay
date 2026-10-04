# A model-free lifecycle tutorial

Begin with the [offline installed example](../README.md#first-run-from-the-installed-package).
This second example uses actual PostgreSQL, OPA, registered deterministic MAF tools,
Executor receipts, FormationSession and signed feed checkpoints. It is software
regression material, not an experiment in intelligence growth or a performance comparison.

Use a dedicated PostgreSQL cluster for the tutorial and a native OPA binary from
the existing [setup guide](quickstart.md). Initialization creates fresh owner roles,
databases, keys and input files; its database administrator needs role/database
creation permission. Never substitute a production owner config. The demo directory
must not already exist. Service passwords and private keys remain private there.

Install published 0.5.0 with `[agents]` in the existing activated environment:

```console
uv pip install --no-cache --no-config --default-index https://pypi.org/simple "collective-intelligence-overlay[agents]==0.5.0"
```

Set `CIO_TEST_DATABASE_URL` to the dedicated administrator connection and `CIO_OPA`
to the verified binary. With those explicit variables, Linux/macOS:

```sh
collective-intelligence-overlay lifecycle tutorial --directory lifecycle-demo --database-url "$CIO_TEST_DATABASE_URL" --opa "$CIO_OPA"
```

PowerShell:

```powershell
collective-intelligence-overlay lifecycle tutorial --directory lifecycle-demo --database-url "$env:CIO_TEST_DATABASE_URL" --opa "$env:CIO_OPA"
```

The command registers CSV sum/render procedures, probes them under explicit read-only
verification grants and asks a separate verifier identity to check actual results.
Signed feeds are applied through existing Receiver checkpoints; reachability alone
cannot grant freshness. A accepts the exact sum tool; B uses its own refusing license
policy and does not adopt it. A actually sums two rows to `5.00`, observes two uses
as formation inputs, publishes a candidate/receipt and records unavailable joules.
An owner withdrawal then causes a new receiver assessment to reject the tool.

The output and `lifecycle-demo/lifecycle-results.json` retain opening/closing stock,
Lifecycle/formed Lifecycle, Growth and REUSE→ACCOUNT Handoff. Expected fields include
`receiver_A: ACCEPT`, `receiver_B: REJECT`, `after_withdrawal: REJECT`,
`new_model_generation_requests: 0`, `actual_result: {rows: 2, total: "5.00"}`.
Handoff authority remains `not_granted`; functional growth remains `not_estimated`.
A/B material is explicitly partial with no atomic cross-owner snapshot. Formation
links establish the recorded uses, not novelty or causal improvement. Missing energy
is not zero; reservations are not measured consumption.

The command closes its Store connections and launches no peer/model process. It
retains databases and original records. Keep its dedicated cluster and directory
for inspection/export; archive privately and stop only that cluster when done.
It does not remove or alter your existing services. On a failed run preserve its
directory/log and use a new directory after correction; do not overwrite failure history.

For three separate peer processes and external tools, continue with the original
[network/application tutorial](quickstart.md) and [integration contracts](integrations.md).
Those established paths retain their own authentication, use-time gates and recovery
requirements. Do not run model or research comparison commands for this feature release.
