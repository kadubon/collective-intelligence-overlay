# Architecture and boundaries

Each participant owns a `Store` (one PostgreSQL database/role), a pinned identity
registry, OPA settings and an `Overlay`. The core has no LLM or protocol dependency.
SQLAlchemy handles database operations and Alembic handles explicit migrations.

Capability, Evidence, Event and Revocation are immutable signed wire records.
Decision is a receiver-local record. PostgreSQL keeps record content, DSSE envelope,
receipt time, dependency edges, local decisions, budgets and leases. JSON Schemas
are generated from Pydantic models, not independently maintained definitions.

The host validates types, signatures, references and bounded lineage. Rego is the
only implementation of operational admission rules. OPA runs as a subprocess with
a five-second deadline: one service fewer than a REST deployment, at the cost of
per-call process overhead. The policy bytes and settings are hashed in every decision.

MAF owns tool loops and workflow execution. A2A owns discovery-card serialization,
JSON-RPC and transport lifecycle. MCP owns tool discovery/calls and its HTTP protocol.
Overlay data is carried by the required extension URI
`https://github.com/kadubon/collective-intelligence-overlay/extensions/v1`.
This URI is an identifier, not a claim that an external registry approved the extension.

`reference.py` and `peer.py` provide the installed deterministic business functions.
Generic capability admission has no CSV-specific branch. The reference peers only
execute known local functions after digest comparison; received Python is never run.
An application's own trusted actuator must enforce its input contract and permissions.

There is no central manager requirement, broker, custom scheduler, distributed
registry, vector store or consensus algorithm. The demonstration coordinator only
drives a finite reproducible test. Other A2A implementations can participate if they
implement the declared extension and configure compatible trust/policy locally.

Trust in agents and trust in infrastructure differ: peers' generated statements are
untrusted, while each participant trusts its host, DB administrator, OPA executable,
key registry and installed checker. This boundary is detailed in [security](security.md).
