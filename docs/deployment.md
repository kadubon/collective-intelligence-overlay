# Deployment, backup and upgrades

## 0.3.2: capacity recovery and native Mac

Stop old writers and take a consistent backup before applying migration 0015.
It adds an ordered owner/state index and rewrites no original record, signature,
invocation ID/state, lease, reservation, balance or remote call map. Restore a
tested backup for rollback. The migration/interrupt/restore regression uses an
actual published-0.3.1 wheel fixture and compares every original table row.

[Native Mac setup](quickstart.md) uses `brew --prefix postgresql@17` for Intel or
Apple Silicon, rather than a fixed path. Its isolated trust-auth cluster is for
development; production still needs restricted roles and SCRAM/TLS below.
Docker Desktop and system-wide Gatekeeper changes are not required.

After worker loss, list with `invocation-cleanup --dry-run`, then apply a finite
batch using that owner's config. New-claim capacity/budget refusal also makes one
bounded pass. Fencing precedes logical slot recovery. Positive undispatched proof
releases allowance once; dispatched effects remain UNKNOWN/held. Query original
invocation/provider IDs and retain their saved mappings. Cleanup does not stop
host tasks or reconcile effects. Never resend or top up merely because of expiry.
See [API bounds and reasons](api.md).

Version 0.3.1 requires Python >=3.12, PostgreSQL, an OPA 1.21.0
executable, and an HTTPS reverse proxy. No broker is needed. Local tests can use
Windows clients plus PostgreSQL under WSL. Container operation is described in the
tutorial; validation results distinguish binary tests from container tests.
The default development database is PostgreSQL 16.15. See
[compatibility](compatibility.md) for exact tested Python/OS combinations; the
metadata range is distinct from measured runtime support.

Provision one database and restricted runtime role per owner. The bootstrap account
creates roles/databases and is not used by peer processes. Revoke cross-owner CONNECT
and schema privileges; do not distribute a superuser URL to agents. Configure
PostgreSQL SCRAM authentication and TLS for non-loopback connections. The runtime
role needs its own record/decision/lease tables, not other owners' credentials.

The trusted host service owns DB writes. If untrusted code shares its OS account or
DB role it can evade the library; process separation is an operational prerequisite.
The reference setup's random keys are a development convenience. Production key
provisioning/rotation must be performed by the participant's operator.

For 0.3.1, stop every old writer and take the consistent backup below
before applying migrations 0013 and 0014. They add owner-local instance/command receipts
and cause/invocation indexes on existing selections. Original DSSE envelopes,
decisions, invocation IDs/states, leases and reservations are retained. Missing
legacy cause contracts, counts, reasons and reissue times stay unknown; original
record sequence orders the known history. Keep each application's trusted Goal
configuration and installed reconstruction manifests with the backup.
Do not run a 0.3.0 writer against the new selection/observation projections.
CLI `reobserve` consumes trusted `--goal-file` configuration; it does not install
checkers. Restore installed bindings through the existing host factory, inspect
old uncertain invocations by their original ID and reconcile before a new attempt.
Restart does not reset reissue limits. Replay of a cooldown/satisfied receipt is
historical; use a new explicit owner command for a later observation. Rolling
upgrades have not been established. See [the API](api.md) for refusal states.

0014 adds remote-call references, not an execution-state table. Stop old callers
and providers before moving a host to the new ID rule. Keep legacy remote IDs and
query their original provider manually (`operation="invocation"`) when no mapping
exists; never recompute them as new calls. Restore persisted host/session IDs and
installed bindings after restart. For new nested calls, query saved references by
the original parent invocation; do not repeat an UNKNOWN parent or its children
under a new ID. A child's completed result does not release a parent's held allowance.

Before first start: protect config/key/artifact paths, configure pinned peers and
verifier methods, run `check-config`, then `migrate`, then `doctor`. Start one `peer`
process per owner. The ASGI server binds loopback; forward only through authenticated
HTTPS infrastructure. Preserve Authorization and A2A extension headers. Disable public
request-body logging and cap proxy body sizes to 256 KiB. Stop intake before shutdown.

Backup procedure:

1. Stop new work and wait for active leases to settle or expire.
2. Use PostgreSQL `pg_dump --format=custom` for each database, with credentials in
   the standard protected PostgreSQL credential mechanism, not a command-line password.
3. Back up the owner's artifact directory, config and key material separately with
   appropriate access control/encryption. Record package version and policy digest.
4. With every peer and writer stopped, restore into a fresh owner database with
   `pg_restore`, restore protected artifacts, point the protected config at that
   database, and run `migrate --config PATH`.
5. Before starting peers, run `restore-state --config PATH`. This rotates the
   source feed generation, clears all receiver cursor/freshness checkpoints and
   increments subject revisions in one transaction. Old feed and inspection cursors
   must restart. The operation preserves signed records, tombstones, leases,
   reservations, decisions and invocation results; repeating it rotates again.
6. Run `doctor`, record/signature checks and reconcile work since the backup with
   external providers before enabling use. Run full synchronization with peers and
   scoped requalification. Do not reuse cached ACCEPTs or delete known revocations.

`restore-state` is an offline operator command, not a remotely exposed peer action.
It cannot prove that writers are stopped or reconstruct records missing from an old
backup. Restoring an old budget or invocation ledger can lose knowledge of later
spending/effects. Keep execution disabled until that gap has been reconciled; fresh
feed generation is not proof that the business ledger is current. Other receivers
must explicitly restart when they observe the changed source generation, retaining
their previously received withdrawals.

The integration suite exercises actual `pg_dump --format=custom` and `pg_restore`
on the signed 0.1.0 database fixture, then migrates the restored database. It checks
original envelopes, PASS/FAIL/UNKNOWN, withdrawal, leases and remaining budget.
Both PostgreSQL client tools must be on PATH. Windows developers using the test
cluster in WSL may set `CIO_PG_TOOL_PREFIX='["wsl","-e"]'`; credentials for commands
inside WSL must be available to PostgreSQL there. This test is separate from
operator-specific encrypted artifact/key backup and full production disaster recovery.

Never delete active leases to make recovery look successful. Expired workers may
have produced external effects: reservations remain charged and results require
reconciliation. DB result commits and lease completion are atomic; a lost response
does not authorize a second external side effect. A2A transient task memory is not
the durable business ledger. Long-running remote tasks are outside this initial server.

0.2.0 to 0.2.1 requires stopping every old peer/worker before migration 0009.
It adds reservation disposition/release reason to invocation projections without
rewriting signed records, leases, results or balances. Existing rows are marked
`legacy_unknown`, including those formerly called reserved; none is automatically
refunded. Reconcile them using external evidence. Do not run old workers against
the upgraded database; rolling-upgrade safety has not been established.

Version 0.3.0 follows migration 0009 with 0010 (durable local work
selections), 0011 (owner/state invocation index), and 0012 (owner/creation selection
index). These changes preserve existing invocation dispositions, lease fences,
results, balances and original signed records. Stop all old workers, retain keys
and artifacts with the database backup, migrate forward, and restart only the
validated version. Capability v3 and local work Event v3 are distinct record schema
changes; the package version does not change every record's schema. Compatibility
with old live peers or rolling upgrades is not established.

The staged migration regression checks actual 0.2.0 records at the 0009 checkpoint
before upgrading to head. A separate actual-0.2.1 fixture contains reserved,
dispatched, consumed, released and response-unknown invocations. Its complete
record, budget, lease and invocation rows survive upgrade and actual PostgreSQL
dump/restore unchanged. Recovery-generation rotation does not release allowance;
later cancellation refunds only the still-provably-undispatched reservation once.

For new 0.2.1 invocations, result lookup and cancellation can release a still-owned
undispatched expired reservation while atomically fencing its worker. Dispatched
or mismatched/legacy ownership remains held. A failed cleanup/unknown DB commit
must be inspected, not followed by an operator balance overwrite or a new-ID retry.
The lower-level trusted-host Store lease API and FormationSession keep their existing
contract; this patch does not retroactively reinterpret their costs or old leases.

Upgrades: back up, stop work, review compatibility, install a tested wheel, apply
forward Alembic revisions explicitly, and requalify changed dependencies. Destructive
downgrades are unsupported; restore a verified backup instead. Test recovery against
your own data/identity infrastructure before production use.

### Stopped-writer 0.3.2 CSV compatibility upgrade

The old `peer --reference` application has no `drain` command. Stop incoming
callers first, ask the service manager for graceful termination, wait for the
original peer processes to exit, and inspect unfinished invocation/lease rows.
The POSIX regression uses SIGTERM, waits for actual termination and confirms new
connections fail; it never substitutes a forced kill for completed work. An
uncertain original remains UNKNOWN with held allowance. This legacy loopback
compatibility check does not establish an HTTPS production deployment or a
rolling upgrade.

Use a separately installed 0.4.0 candidate interpreter for the following offline
commands; retain the original 0.3.2 installation and verified backup. The URLs,
keys, execution environment and CSV binding/checker contracts remain pinned.
`CIO_BACKUP_DATABASE_URL` names the operator backup connection;
`CIO_UPGRADE_DDL_URL` names the operator connection to that owner's database.

```text
python -m collective_intelligence_overlay.cli backup --config legacy/config.json --directory legacy-backup
python -m collective_intelligence_overlay.cli verify-backup --directory legacy-backup
python -m collective_intelligence_overlay.cli migrate --config legacy/config.json --database-url-env CIO_UPGRADE_DDL_URL
python -m collective_intelligence_overlay.cli peer --reference --config legacy/config.json
```

An old demo database is owned by its runtime role. The operator must transfer
database/schema/table ownership before migration, then explicitly grant runtime
CONNECT, schema USAGE, table DML and sequence USAGE/SELECT. Revoke schema CREATE
and Alembic-version writes. Ownership transfer can change the former owner's ACL;
regrant and verify CONNECT as well as DML. The new compatibility CLI uses the same
owner lock, readiness, drain and resume operations as installed applications.
Original result reads preserve old fields; the added invocation argument digest
does not fill missing legacy provider-map argument identities.

For recovery against an available, stopped, unrewound original, set the private
`application_settings` file to `{"recovery_reference_config":"preserved-reference.json"}`.
The relative path is resolved beside that settings file and points to an
operator-preserved original config outside the backup directory. Register the
query on the upgraded original before taking its coherent backup. Restored
`peer --reference` registers `reference-recovery-state` with an unchecked
candidate and an owner-only read-only verification grant. Offline `restore-state`,
full source sync, `recovery-review --checker reference-recovery-state`, and a
separate explicit `resume` follow the existing recovery procedure. A matched
original-state comparison creates no independent PASS and cannot resend or refund
old UNKNOWN calls. Missing originals keep intake closed.

The source-only `scripts/run_upgrade_032.py` protocol runs actual normally installed
0.3.2 and candidate peers. The Linux minimum-Python installed-package gate requires
its signed-byte/old-column, original-ID, protected-role, closed-restore and CSV
business assertions. Its shared reports exclude private homes and backups.

Migration 0020 adds the local restore publication boundary without changing signed
history. After restoring an older closed generation, run offline `restore-state`
again: migration does not fabricate a historical boundary. The document recovery
query distinguishes positively ordered post-restore full-sync overhead from business
originals, while retaining all signed costs in storage and the core recovery proof.
Missing pre-restore work or costs remain UNKNOWN and intake stays closed.

Migration 0007 adds scoped history projections and bounded backfills of local
decisions. Original signed bodies/envelopes and decision bodies are preserved.
Decision writes share the existing transactional publication counter so inspection
pages cannot skip late commits; decisions are still excluded from the shared feed.
The counter is a local committed prefix, not a count of shared records.

Migration 0008 adds a GIN-indexed dependency projection and backfills capability
records in batches of 128. It preserves original signed bodies/envelopes and leaves
legacy dependency issuers unknown. Apply it with peers stopped as part of the same
forward migration procedure.

The demo leaves random `cio_...` roles/databases for inspection. Remove only those
whose names match the generated config after stopping their peers and checking that
no retained work depends on them. It never drops unrelated databases automatically.

## Change an application, checker or allocation setting

Keep the current installed factory, protected settings, exact binding/checker pins,
operator choices and coherent backup until a replacement is accepted. The operator
owns this procedure; a proposal, model output or remote manifest cannot perform it.
Use the existing staged Registry operations for callable/builder/checker bindings.
For the packaged document host, use `app.stage-change`, independently check its
exact staged digest, and use `app.promote-change` on one to eight actual protected
inputs. The [API](api.md) describes the fields, grants, recorded choice and restart
pins. A completed probe or generated candidate creates no independent PASS.

Allocation is trusted application configuration, rather than an executable remote
proposal. The document factory reads its validated `allocation` object from
`application_settings`; an arbitrary installed factory can use the same existing
`AllocationPolicy` and `allocate` API. Apply a change through this finite procedure:

1. Record the previous and candidate policy values/digests, exact installed factory,
   goals, checker contract and protected input set before the trial. Keep the normal
   concurrency, permission, budget and time bounds. A new threshold or mode is a
   candidate setting; copying it into a running production owner is not a trial.
2. Start fresh isolated trial owners with their own keys, restricted databases,
   result caches and artifacts using the existing setup and installed factory.
   Grant read-only inputs or separate test-provider resources. Do not replay a
   production effect, share a live owner's role, or reuse its unknown call IDs.
3. Run bounded work through the standard owner `run`/Steps/Executor path and have
   the separate checker verify the declared business and protected cases. Retain
   the original receipts, signed allocation policy/rule digests, observations,
   resource units and every refused/UNKNOWN/censored task. The installed
   [matched experiment](production-experiments.md) is the executed reference for
   isolated static/adaptive settings and independent checks, including its negative
   result. Its source runner does not provide arbitrary policy autotuning.
4. Keep the comparison basis and exact original evidence references in the owner's
   private CAS and existing signed recommendation Event. Record whether the checker
   contract is unchanged, changed or unknown. A changed source/calibration uses a
   new checker digest/version, new goal pins and new independent evidence; old PASS
   does not transfer. A recorded comparison label does not establish statistical
   comparability. Report changed criteria separately from an old success fraction.
5. The operator reviews the scoped results before stopping/draining the production
   owner and saving the accepted configuration. Retain the previous settings and
   evidence. Run `check-config` and `doctor`, restart with explicit pins, inspect
   current signed allocation digests and apply ordinary current admission. FAIL,
   UNKNOWN or a protected regression keeps the previous production setting.
6. Roll back by stopping intake and restoring the retained configuration/pins through
   the same current checks. Keep the trial, choice and production history. A rollback
   cannot erase previous effects or uncertain reservations.

The host closes intake with `APPLICATION_PINS_SAVE_FAILED` if staged-choice settings
cannot be published. Repair the owned storage fault and restart from the last
persisted settings before resuming work. A committed historical choice is not a
request to reapply a transition after rollback. All twelve updated native source
and normally installed three-owner fault protocols pass this boundary on the
fixed candidate pair; final immutable-tag gates remain required before publication.
This procedure introduces no automatic global
approval, policy search or new execution/state ledger.
