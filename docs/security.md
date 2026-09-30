# Security and threat model

Version 0.3.1 distinguishes expected hostile Proposal input from host faults.
Pure DSSE/type and SDK wire parsing have narrow rejection boundaries. Collection
isolates malformed whole replies per peer and authenticates sibling proposals
individually; selection checks the owner goal, exact references and installed builder
before saving valid alternatives. Expected rejection cannot veto valid siblings or
other peers. Invalid raw payloads and peer error messages are not business records.
Bounded local category observations remain private and do not change admission,
permissions, budgets, counterexamples or UNKNOWN. Internal storage/assessment faults
and cancellation propagate. Outstanding peer requests are joined during cleanup.

Both overlay peers and standard A2A service clients restrict SDK HTTP traffic to
the configured JSON-RPC endpoint and its Agent Card path. Response bytes are capped
before protobuf parsing, including chunked responses; compressed responses are
rejected. Redirects, environment proxies and transport retries are disabled.
This bounds application buffering, not the operating system's socket buffers.

0.3.0 proposals cannot change registered goals, checkers, allowlists, permissions,
trust groups or allowance. Generic submit/feed does not authorize work exchange:
each proposer needs a registered public contract and named owner. Only configured
peers receive an opportunity. Private checker arguments are omitted; hashes are
commitments, not encryption. Exclude credentials, personal data, internal paths
and held-out answers from shared inputs. Schema/byte/alternative bounds and finite
repair apply to MAF output before host validation. The structured proposer has no
tools. An unverified checker has no ordinary acceptance authority; calibration
probes cannot certify themselves. Materialized artifacts contain data for installed
factories, never received imports, shell commands or a workflow language.

The trusted computing base is the participant's host, DB administrator, installed
code/checkers, OPA binary/policy, key registry and clock. Agents, model output, remote
records and tool output are untrusted. This is not a trustless database/network system.

Each peer has a distinct Ed25519 key. PyJWT validates short-lived EdDSA bearer tokens
against pinned keys, audience, issuer, subject and expiration. DSSE separately binds
record contents to the claimed issuer using securesystemslib. Direct submission must
match the authenticated connection identity. Discovery can transfer original signed
records without converting transport identity into verifier authority.

Production endpoints require HTTPS. Terminate TLS at an operator-managed reverse
proxy; the bundled server binds loopback. Exact endpoint allowlists, disabled redirects
and disabled environment proxies prevent agent-supplied endpoint substitution. The
operator must control DNS/network egress for approved domains; arbitrary Internet
discovery is not supported. The demonstration explicitly permits literal-loopback HTTP.

Secrets and policy are host configuration, not agent context. Run model/tool processes
as separate OS users without write access to keys, policy files or DB-owner credentials.
The reference service is a trusted host process; importing middleware into an arbitrary
compromised Python process does not isolate it. Use existing OS/container isolation
for user code. Never execute received code in the host.

All operations are denied unless registered. The host checks permission scope at use;
tool descriptions cannot add permissions. A2A enforces an input byte limit before SDK
parsing, bounded execution time and concurrency. Graph and model collections are bounded.

Candidate verification is an explicit operator privilege. A binding may allow named
verification callers only when declared read-only; the normal caller list and other
checks remain in force. Wire metadata cannot set the trusted `verification_granted`
flag. That low-level API is part of the trusted host boundary, not an agent tool.
Probe results are not evidence of correctness and do not authorize ordinary reuse.
The effect declaration does not sandbox a malicious or compromised implementation.
MCP uses the official HTTP transport with no redirect/proxy inheritance and explicit
tool allowlists. The reference MCP server is loopback-only and contains no private data;
it is not an Internet deployment template.

Artifact paths are content digests within an owner directory, rejecting traversal,
symlinks, oversize content and altered bytes. Host ownership remains essential: this
does not defend against an administrator racing filesystem operations. Evidence
sharing is disabled by default. Enabling it shares the owner's signed records with
configured peers; do not place secrets in shared metadata or artifacts.

There is no transparency-log upload. Normal CLI errors omit payloads and credentials.
Do not use debug tracebacks in shared logs. No code claims arbitrary secret detection
inside domain data. The application owner must redact sensitive inputs before sharing.

0.2.1 allowance release requires database ownership and a reserved phase; it is
never authorized merely by an AdmissionDenied exception or a cancelled Python
await. Authenticated callers authorized for a binding can still consume inspection
resources with rejected requests. Execution allowance release does not make OPA,
DB or authentication free. Existing message/argument bounds, request deadlines and
configured A2A concurrency limits remain in force; no new rate-limit service is added.

Tests cover tampering, identity/audience/expiry, unknown schemas, stale evidence,
permission denial, bounded input, revocation, cancellation and stale worker fencing.
External penetration testing, malicious administrator resistance, multi-organization
key management and long-running availability have not been established.

0.3.1 reobservation is owner-local and absent from peer/model tools. Its request IDs,
reason labels, lifetime, cooldown and count are bounded. Stable owner/goal grouping
prevents a target/checker revision from hiding an unresolved old execution. The
existing feed transaction serializes instance and choice creation; execution still
uses the existing budget/invocation/lease lock order. No observation issues a grant
or refunds resources. Selection requires persisted terminal/fence/release proof,
keeps ambiguous legacy mappings for reconciliation, and refuses a second attempt
while prior work is pending or uncertain. Original signed facts remain immutable.

0.3.1 logical call identity comes from trusted host execution context or the MAF
SDK's public tool-call ID, with owner/caller/session/parent namespaces. Models supply
business inputs only. Neither a new call ID nor a saved reference grants provider
permission: actual purpose, caller authentication, local admission and allowance
remain provider-owned. Same-ID content changes conflict. Result queries use the
saved destination and original provider ID, scoped to the trusted local caller;
old unknown mappings are never reconstructed as fresh operations.

Verification of a local A2A proxy uses the already-qualified provider's ordinary
reuse contract. A local verification grant does not create a remote verification
grant or bypass the provider's independent PASS/freshness requirement. Direct
provider verification requests retain their separate read-only grant check.
