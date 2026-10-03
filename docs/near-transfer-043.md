# v0.4.3 sensitivity-calibrated near-transfer study

This source-only study keeps the published [0.4.2 observations](accumulation-042.md)
unchanged. Its SQL floor, calibration floor/ceiling and failed composition assay
do not justify extending that confirmation. The new question is transfer of a
learned executable contract to unseen inputs in a new receiver, followed by
formation of an easier composition. It does not test distant-domain generalization.

The [pilot protocol](studies/near-transfer-043/pilot-v1-protocol.json) fixes two
waves: four ordinary-M scratch examples for each of S1/S2, K1/K2 and F0/F1, then
six unused worlds for the selected level of each family. Select the proportion
closest to 0.5; ties use the ascending declared level. Neither C minus M nor
Full minus Empty influences selection. Exact binomial intervals are descriptive;
shared pilot conditions can induce dependence. SQL/calibration must each reach
30–70%, formation 20–80%, reference and completion at least 90%. Natural M/C
stock must reach a fresh receiver and succeed by retrieved executable use.
Otherwise record `assay_not_ready` and do not start confirmation.

The shared cap covers at most 256 generation requests, 400,000 charged input/output
tokens and 14,400 seconds. Pilot uses at most 60 requests in two waves; no model
warmup is excluded. A conservative 300-second allowance covers preceding service
startup, and physical cleanup has at most 300 additional seconds without inference.
The actual driver wall and conservative startup charge are separate observations.
The fixed CPU request uses the locally installed Gemma4:e4b digest, no cloud or
pull, serial inference, 4096 context and 1024 output tokens. The first screen request
bears cold loading; locked validation follows screening with the same server.

The experimental runtime is the exact published noneditable 0.4.2 wheel, checked
by file hashes and module origins. New scientific sources have their own fixed
manifest. This is distinct from the final 0.4.3 package/native release gate.

For a prepared local checkout, install its frozen dependencies and the declared
wheel into a noneditable environment; provide an owned PostgreSQL connection,
OPA and Caddy through `CIO_TEST_DATABASE_URL`, `CIO_OPA`, `CIO_CADDY`. The ordinary
production setup and service requirements are in [deployment](deployment.md).
These are the actual study commands, using that environment's Python:

```powershell
python scripts/run_near_transfer.py prepare --protocol docs/studies/near-transfer-043/pilot-v1-protocol.json
# Commit and push the protocol and its sources before generation.
python scripts/run_near_transfer.py pilot --protocol docs/studies/near-transfer-043/pilot-v1-protocol.json --prereg-commit COMMIT --output .local/near-transfer-043-pilot-v1 --home .local/private-near-transfer-043-pilot-v1
python scripts/analyze_near_transfer.py --run .local/near-transfer-043-pilot-v1 --output .local/near-transfer-043-offline-v1
python scripts/prepare_gemma_public.py --source .local/near-transfer-043-pilot-v1 --output .local/near-transfer-043-public-v1
```

Outputs are exclusive: a changed source, existing output or uncertain prior request
cannot silently resume or regenerate. Reference SQL and latent parameters remain
outside proposer input. Short schemas require executable fields; missing solutions
are never completed from references. Hidden checker verdicts are not draft feedback.
SQL uses the existing bounded read-only SQLite sandbox, never operational PostgreSQL.
Composition runs the existing registered MAF builder/workflow, with observable
parameter/order effects and independent inputs. Scratch construction is allowed
without prior CIO PASS for that candidate.

Per-offer Q and restricted time/token endpoints retain failed offers, using common
failure horizons 600 seconds / 10,240 charged tokens. These endpoints differ from
actual consumption. Missing usage retains the reservation and a measured/charged
interval. Receiver setup/import are fixed costs; online retrieval, admission and
checks fall inside probe timing. Inclusive parent and nested process walls are not
added. Tokens and seconds stay separate; future maintenance and energy are unknown.

If all entrance conditions pass, a separate pushed confirmation protocol must first
fix independent world count, selected levels, feasibility, pairing and order. The
default plan is six worlds, M/C with four training episodes each, then Full/Empty
near probes and one formation probe, at most two drafts per probe. Original
providers must be physically absent; qualification inputs differ from probe inputs.
Empty cognitive views preserve safety history. Empty trained worlds remain in the
denominator. No confirmation performance is established by this methods document.

Worlds are the independent units. The three declared contrast directions are
M Full minus Empty, C Full minus Empty, and C Full minus M Full: higher Q and lower
restricted resources. Interest differences are 0.15 Q and 20% resources, with 0.10
quality harm margin; all families and contrasts are reported without confirmatory
p-value claims. Small-N descriptive intervals cannot establish equivalence. A
conditional fixed-cost recovery F/s is meaningful only at the same observed quality
and cost unit with positive marginal savings. Otherwise no finite break-even is
claimed. Model signatures and raw hashes establish identity/consistency, not truth
or attestation against a malicious operator.
