Operator starter for Collective Intelligence Overlay

Generate these files with `collective-intelligence-overlay starter --directory NEW_DIR`.
The Python application illustrates explicit local registration and publishes only
a generated candidate. It creates no independent PASS or permission to reuse.
Select the installed copy with application factory
`collective_intelligence_overlay.starter.application:configure`, or adapt it inside
your own explicitly installed and reviewed application package.

Production setup uses an existing restricted PostgreSQL runtime role, an explicitly
installed OPA binary, and an operator-supplied HTTPS certificate/private key. Never
give the runtime role database ownership or DDL rights. Migration uses a separate
bootstrap connection. Do not copy demo credentials or disable TLS verification.

Caddy is an external Apache-2.0 reverse proxy, not bundled or automatically installed.
Set CIO_PUBLIC_ADDRESS, CIO_TLS_CERTIFICATE, CIO_TLS_PRIVATE_KEY and CIO_LISTEN_PORT
explicitly, validate the Caddyfile with the reviewed Caddy version, and run the
peer on its configured loopback listen_port. Authorization and A2A extension headers
pass through to the existing authenticated application. Public metadata and private
credentials remain in separate files. No artifact directory is served by this proxy.
