# Troubleshooting

| Observation | Check / action |
| --- | --- |
| Missing PostgreSQL connection | `doctor`, URL/port, server readiness, owner-role CONNECT rights |
| Missing OPA / UNKNOWN policy | Set absolute `CIO_OPA`, verify downloaded checksum, run `opa check` on packaged policy |
| REQUALIFY after environment change | Create scoped new evidence; do not edit old PASS |
| UNKNOWN after restart | Refresh the producer through authenticated discovery; old source freshness is intentionally lost |
| REJECT after demo | The demo revokes the aggregate; a restart does not clear that tombstone |
| Same record ID conflict | Preserve old record; choose a genuinely new version/evidence ID for new content |
| Stale worker / exhausted budget | Reconcile lease and external effects; do not refund unknown outcomes automatically |
| SDK import missing | Install the `agents` extra; provider example also needs `model` |
| More than bounded records/graph | Narrow/archive the owner dataset after retention review; do not silently ignore excess evidence |
| Existing demo directory | Use a new directory; the tool intentionally does not overwrite keys/data |
| Model example refuses to run | Explicit `--allow-model-calls` plus configured provider are required |
| Publication fails | See [release procedure](releasing.md); never bypass OIDC/environment protection |

Default CLI errors are redacted. Local `CIO_DEBUG=1` can reveal a traceback and may
include sensitive exception context; use only in a private development console.
Peers write no request bodies to normal access logs. Share only sanitized diagnostics.
