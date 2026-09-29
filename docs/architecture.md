# Architecture and boundaries

Each participant owns a `Store` (one PostgreSQL database/role), a pinned identity
registry, OPA settings and an `Overlay`. The core has no LLM or protocol dependency.
SQLAlchemy handles database operations and Alembic handles explicit migrations.

Capability, Evidence, Event and Revocation are immutable signed wire records.
Decision is a receiver-local record. PostgreSQL keeps record content, DSSE envelope,
receipt time, dependency edges, local decisions, budgets and leases. JSON Schemas
are generated from Pydantic models, not independently maintained definitions.

Admission loads a bounded dependency closure in one repeatable-read transaction.
Capability queries constrain the full subject digest and requested issuer in SQL;
v2 dependencies carry exact issuers. Legacy references without an issuer retain
collisions so qualification can reject ambiguity. Cycle detection uses issuer plus
the full subject identity, rather than treating equal names and versions as equal
capabilities. Evidence and revocation queries remain bounded and preserve dissent.

The host validates types, signatures, references and bounded lineage. Rego is the
only implementation of operational admission rules. OPA runs as a subprocess with
a five-second deadline: one service fewer than a REST deployment, at the cost of
per-call process overhead. The policy bytes and settings are hashed in every decision.

MAF owns tool loops and workflow execution. A2A owns discovery-card serialization,
JSON-RPC and transport lifecycle. MCP owns tool discovery/calls and its HTTP protocol.
Overlay data is carried by the required extension URI
`https://github.com/kadubon/collective-intelligence-overlay/extensions/v2`.
This URI is an identifier, not a claim that an external registry approved the extension.

`reference.py` and `reference_peer.py` provide the compatibility business application;
`peer.py` provides the generic peer. `examples/document_application.py` registers
an external application through the binding API.
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

0.3.0 adds operator `Goal` configuration, signed `Opportunity`/`Proposal` records
and one durable owner-local `Selection` per opportunity. Discovery uses the same
bounded qualification snapshots; allocation describes a finite goal window and
creates no grants. Steps supplies installed-builder inputs to Executor, whose
invocation, lease and allowance rows remain the only execution lifecycle. The
host materializes results through an installed factory, publishes observed
FormationSession receipts and persists its goal's exact new target. Independent
checking then creates evidence. No distributed goal store, background queue or
scheduler is introduced.

Binding schema 2 pins saved parameters/source/environment/components; Capability
schema 3 distinguishes construction inputs from live runtime dependencies.
Local work Event schema 3 carries observations without a receipt or verdict.
Original older signed bytes remain immutable. [Semantics](semantics.md) and
[compatibility](compatibility.md) define versions and conservative failure rules.
Owner event pages, target assessments and opportunity cohorts use existing
accounting and distinguish their observation times.
