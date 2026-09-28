# Security and threat model

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

Tests cover tampering, identity/audience/expiry, unknown schemas, stale evidence,
permission denial, bounded input, revocation, cancellation and stale worker fencing.
External penetration testing, malicious administrator resistance, multi-organization
key management and long-running availability have not been established.
