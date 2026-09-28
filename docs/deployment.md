# Deployment, backup and upgrades

The reference network deployment uses Python 3.12, PostgreSQL 16, an OPA 1.21.0
executable, and an HTTPS reverse proxy. No broker is needed. Local tests can use
Windows clients plus PostgreSQL under WSL. Container operation is described in the
tutorial; validation results distinguish binary tests from container tests.

Provision one database and restricted runtime role per owner. The bootstrap account
creates roles/databases and is not used by peer processes. Revoke cross-owner CONNECT
and schema privileges; do not distribute a superuser URL to agents. Configure
PostgreSQL SCRAM authentication and TLS for non-loopback connections. The runtime
role needs its own record/decision/lease tables, not other owners' credentials.

The trusted host service owns DB writes. If untrusted code shares its OS account or
DB role it can evade the library; process separation is an operational prerequisite.
The reference setup's random keys are a development convenience. Production key
provisioning/rotation must be performed by the participant's operator.

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

Upgrades: back up, stop work, review compatibility, install a tested wheel, apply
forward Alembic revisions explicitly, and requalify changed dependencies. Destructive
downgrades are unsupported; restore a verified backup instead. Test recovery against
your own data/identity infrastructure before production use.

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
