# Native TLS proxy build

The production candidate uses Caddy **v2.11.4+cio.1**, not the upstream release
binary. The original official Windows binary failed `govulncheck` with 28 affecting
findings on 2026-10-01. Its audit is retained; successful HTTP tests did not make
that binary acceptable. No numerical production gate was changed.

This build retains upstream v2.11.4 commit
`e2eee6a7fce366321294c9c2a79f3146891dcbdf`, freezes the security dependency updates
in the adjacent `go.mod`/`go.sum`, and builds with native Go 1.27.1. The only Caddy
source changes are the two type substitutions in `cel-v2.patch`, required by
cel-go 0.30's public `NewCall` API. Original Apache notices stay in the source.
`go test ./modules/caddyhttp/... ./modules/caddytls/...` validates these changes.
No additional proxy implementation, Caddy plugin or automatic pip download is added.

Install native Go 1.27.1 from [Go downloads](https://go.dev/dl/) and Git explicitly.
From this checkout, run `uv run python scripts/fetch_caddy.py`. The script clones
the exact source, builds, verifies modules, runs upstream tests, audits the actual
native binary and saves licenses and a CycloneDX SBOM. CI uses pinned setup-go to
install this exact toolchain. The executable is `.local/proxy-build/caddy`
(`caddy.exe` on Windows); use it with the packaged Caddyfile. Build tools and the
proxy remain separate from the Python wheel and its runtime dependencies.
The checkout uses `.local/proxy-build/caddy-source`; the executable is a separate
`caddy`/`caddy.exe`. The first 0.4.0 native CI run exposed the previous POSIX name
collision before security or application gates ran. Its failure remains retained.

The packaged listener explicitly enables HTTP/1.1 and HTTP/2 using the standard
[Caddy server protocols option](https://caddyserver.com/docs/caddyfile/options#protocols).
The declared A2A/MCP profile uses these TCP transports. A native Windows test found
an HTTP/3 UDP listener bind refused for a dynamically chosen port; HTTP/3 is not
required by the profile. The configuration avoids that additional listener without
changing TLS verification, authentication, operation bounds or acceptance targets.

## Security review

`govulncheck` 1.8.0 must return zero affecting/package findings. The only reviewed
module-level finding is [GO-2026-5932](https://pkg.go.dev/vuln/GO-2026-5932): unsafe,
unmaintained `golang.org/x/crypto/openpgp`, for which no fixed version exists.
The native build's complete `go list -deps ./cmd/caddy` must contain **none** of
the affected OpenPGP packages, and the binary scanner must not report an affected
package or symbol for this finding. This is a reviewed nonapplicability judgment,
not an ignored linked vulnerability. Any new finding fails the gate. The scanner
version, database metadata, complete stdout/stderr, packages and binary buildinfo
are retained. This is neither an independent security audit nor a future guarantee.

## License review

Caddy is Apache-2.0. `go-licenses` 2.0.1 checks the actual native dependency graph;
unknown or other licenses fail. Apache-2.0, MIT, BSD-2/3-Clause and CC0-1.0 notices
are retained using its `save` command. Preserve the saved notices with any binary
redistribution. The source and build inputs remain available at the pinned commit
and module versions, including the two-line modification.

Two additional license obligations were reviewed rather than called permissive:

- Chroma 2.24.1's `COPYING` contains MIT for code and **OFL-1.1** for the embedded
  Liberation Mono font. Retain the combined COPYING and font copyright/reserved
  names. This build does not modify or separately sell the font. See the
  [OFL text and FAQ](https://openfontlicense.org/).
  The tool's report/check identify OFL, but its save command lacks an OFL source
  obligation handler and refuses Chroma. Only that save operation excludes Chroma;
  its exact module's complete COPYING is copied alongside the other saved notices.
  License check still covers Chroma and fails unknown classifications.
- go-sql-driver/mysql 1.9.3 is **MPL-2.0**, including file-level source obligations.
  This build does not modify its source. Redistributors must retain its license
  and disclose availability of the exact covered source at
  [v1.9.3](https://github.com/go-sql-driver/mysql/tree/v1.9.3), or provide that source
  with the binary. The larger executable may retain other component licenses;
  see [MPL 2.0 sections 3.1–3.3](https://www.mozilla.org/en-US/MPL/2.0/).

The tool warns that Go assembly cannot be inspected for hidden external
dependencies. This build disables cgo and records selected packages/files in the
SBOM, including assembler/header assets; Go's runtime is BSD-3-Clause. Retain
these warnings and review the listed module-owned assembly/header notices.
The root module's license URL defaults to HEAD in go-licenses: the correct Caddy
license is [the pinned commit's LICENSE](https://github.com/caddyserver/caddy/blob/e2eee6a7fce366321294c9c2a79f3146891dcbdf/LICENSE).
Report success only for native targets actually built, audited and tested.

`scripts/check_proxy_sources.py` supplements the non-Go warning using the actual
retained native SBOMs. It matches every assembly/header byte hash to the exact
module/Go 1.27.1 source, resolves literal assembly includes, and preserves full
original source notices, the toolchain LICENSE and each native module notice in
a separate archive. Go-generated `go_asm.h` is identified from the pinned
compiler's `-asmhdr` behavior. Standalone C headers and their declared includes
remain retained separately from the assembly include closure in the CGO-disabled
build. This does not establish semantic absence of hidden dependencies.

For a complete downloaded candidate/report set, run:

```sh
python scripts/check_proxy_sources.py --reports REPORTS --candidate CANDIDATE \
  --cache EXACT_GO_MODULE_CACHE --goroot EXACT_GO_1_27_1_ROOT --output NEW_REVIEW
```

All twelve native reports from run `36817672720` matched 180 distinct original
source/header/include/toolchain-license paths and retained 2,634 module notice
paths. Assembly include resolution had no unresolved path. Altered source hashes,
paths outside the source cache and a CGO-enabled build are rejected. This is a
retained earlier-candidate review; the final candidate needs its own report check.

The final `33898a96` wheel / `965f848e` sdist pair subsequently passed the same
source review on twelve actual native proxy reports. Original archives and
per-file hashes are recorded in the retained input provenance: eight reports from
expanded run `36854239260` and four original Mac reports from `36848916312`.
The proxy/build/review sources are unchanged between those commits. All 180 distinct
source/header/include/toolchain-license paths matched; 2,634 native module notice
paths accompany them. The 2,814-file source/notice archive has SHA256
`9b468f6fe6fec8acadd594802f38832358f524c158ff9cacc02b32b98883d532`.
There were no unresolved literal assembly includes. This supplies the final-pair
source/notice review, with the same limits above; the complete expanded native
workflow and production profile remain separate gates.
