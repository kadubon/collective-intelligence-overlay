"""Actual installed setup, restricted roles and native Caddy for owned test peers."""

import asyncio
import json
import os
import secrets
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

import httpx
import httpx2
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from securesystemslib.signer import CryptoSigner
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from collective_intelligence_overlay.bindings import Binding, Target, fingerprint
from collective_intelligence_overlay.config import Peer, TrustedIdentity, load_config
from collective_intelligence_overlay.demo import free_ports
from collective_intelligence_overlay.models import Scope, Subject, now
from collective_intelligence_overlay.security import Identity
from collective_intelligence_overlay.setup import bootstrap_database, initialize


def stop_process(process, *, kill=False):
    # This harness is also imported by standalone soak/experiment drivers,
    # without pytest's collected integration-module paths.
    helpers = str(Path(__file__).parents[1] / "integration")
    if helpers not in sys.path:
        sys.path.insert(0, helpers)
    from process_control import stop_owned_process

    stop_owned_process(process, kill=kill)


class ProductionMesh:
    def __init__(
        self,
        directory,
        operator_url,
        opa,
        caddy,
        allowance,
        *,
        proxy_seconds=180,
        owners=("producer", "verifier", "receiver"),
    ):
        if (
            not isinstance(proxy_seconds, int)
            or isinstance(proxy_seconds, bool)
            or not (30 <= proxy_seconds <= 3600)
        ):
            raise ValueError("explicit bounded owned-proxy deadline required")
        self.proxy_seconds = proxy_seconds
        if owners not in {
            ("producer", "verifier", "receiver"),
            ("producer", "verifier", "receiver", "newreceiver"),
        }:
            raise ValueError("explicit finite owned peer topology required")
        self.directory = directory
        self.directory.mkdir(mode=0o700)
        # A separately closed free_port() may immediately return the previous
        # owner's port. Keep all eight sockets bound during batch allocation.
        self.ports = iter(free_ports(2 * len(owners) + 2))
        # Administrative CREATE/DROP may need a PostgreSQL checkpoint. This
        # bounded cleanup connection is never handed to runtime peers; their
        # Store/socket/statement/lock bounds remain unchanged.
        self.admin = create_engine(operator_url, connect_args={"timeout": 30}, hide_parameters=True)
        self.names = []
        self.proxies = []
        self.workers = []
        self.logs = []
        self.configs = {}
        self.caddy = os.path.abspath(caddy)
        self.version = subprocess.check_output(
            [self.caddy, "version"], text=True, timeout=10
        ).strip()
        assert self.version == "v2.11.4+cio.1"
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        certificate = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now() - timedelta(minutes=1))
            .not_valid_after(now() + timedelta(hours=24))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(key, hashes.SHA256())
        )
        self.cert, self.key = directory / "certificate.pem", directory / "tls-private.pem"
        self.cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        self.key.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        os.chmod(self.key, 0o600)
        try:
            for owner in owners:
                resource = "cio_mesh_" + uuid4().hex
                runtime = make_url(operator_url).set(
                    username=resource,
                    password=secrets.token_hex(24),
                    database=resource,
                )
                path = initialize(
                    directory / owner,
                    owner=owner,
                    url=f"https://localhost:{next(self.ports)}/",
                    database_url=runtime.render_as_string(hide_password=False),
                    opa=opa,
                    listen_port=next(self.ports),
                )
                config = load_config(path)
                # Names are known before bootstrap: preserve partial failures and
                # clean only these exclusive test resources in close().
                self.names.append(resource)
                bootstrap_database(config, operator_url, Decimal(allowance))
                self.configs[owner] = config
            identities = {
                owner: config.identities[owner].model_copy(update={"methods": ("reference-check",)})
                for owner, config in self.configs.items()
            }
            # Two authenticated test clients grant no execution, checker,
            # proposal or operator permissions and own no service/database.
            # Five callers are needed to exercise owner=16 and caller=4 together.
            self.http_clients = {
                name: Identity(name, CryptoSigner.generate_ed25519())
                for name in ("capacity-client", "capacity-observer")
            }
            identities.update(
                {
                    name: TrustedIdentity(
                        keyid=identity.signer.public_key.keyid,
                        key=identity.signer.public_key.to_dict(),
                        trust_group=name,
                    )
                    for name, identity in self.http_clients.items()
                }
            )
            peers = tuple(
                Peer(identity=owner, url=config.url) for owner, config in self.configs.items()
            )
            self.configs = {
                owner: config.model_copy(
                    update={
                        "identities": identities,
                        "peers": peers,
                        "share_records": True,
                        "tls_ca_certificate": self.cert,
                    }
                )
                for owner, config in self.configs.items()
            }
            for config in self.configs.values():
                _, overlay = config.runtime()
                try:
                    with overlay.store.engine.connect() as conn:
                        assert (
                            conn.execute(
                                text(
                                    "SELECT has_schema_privilege(current_user, 'public', 'CREATE')"
                                )
                            ).scalar_one()
                            is False
                        )
                        assert (
                            conn.execute(
                                text(
                                    "SELECT has_table_privilege(current_user, "
                                    "'alembic_version', 'UPDATE')"
                                )
                            ).scalar_one()
                            is False
                        )
                        for foreign in self.names:
                            if foreign == make_url(config.database_url.get_secret_value()).database:
                                continue
                            assert (
                                conn.execute(
                                    text(
                                        "SELECT has_database_privilege("
                                        "current_user, :db, 'CONNECT')"
                                    ),
                                    {"db": foreign},
                                ).scalar_one()
                                is False
                            )
                finally:
                    overlay.store.close()
        except BaseException:
            self.close()
            raise

    def start_proxies(self):
        for owner, config in self.configs.items():
            self.start_proxy(owner, config.url, config.listen_port)

    def start_proxy(self, owner, endpoint, port):
        path = self.directory / owner / "Caddyfile"
        template = (files("collective_intelligence_overlay") / "starter/Caddyfile").read_bytes()
        if self.proxy_seconds != 180:
            # Dedicated experiment gateways may follow the explicit SDK deadline.
            # Existing native/reference defaults and package template stay at 180s.
            if template.count(b"180s") != 4:
                raise ValueError("owned proxy timeout template changed")
            template = template.replace(b"180s", f"{self.proxy_seconds}s".encode())
        path.write_bytes(template)
        environment = {
            **os.environ,
            "CIO_PUBLIC_ADDRESS": endpoint.rstrip("/"),
            "CIO_LISTEN_PORT": str(port),
            "CIO_TLS_CERTIFICATE": str(self.cert),
            "CIO_TLS_PRIVATE_KEY": str(self.key),
        }
        checked = subprocess.run(
            [self.caddy, "validate", "--config", str(path)],
            env=environment,
            capture_output=True,
            timeout=10,
        )
        assert checked.returncode == 0, checked.stderr.decode(errors="replace")
        log = (self.directory / owner / "proxy.log").open("ab")
        self.logs.append(log)
        self.proxies.append(
            subprocess.Popen(
                [self.caddy, "run", "--config", str(path)],
                env=environment,
                cwd=self.directory,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        )

    def start_mcp(self):
        home = self.directory / "mcp"
        home.mkdir(mode=0o700)
        token = secrets.token_urlsafe(32)
        public, private = next(self.ports), next(self.ports)
        origin = f"https://localhost:{public}/"
        endpoint = origin + "mcp"
        log = (home / "service.log").open("ab")
        self.mcp_audit = home / "calls"
        self.mcp_results = home / "results"
        self.mcp_delay = home / "delay-seconds"
        self.mcp_delay.write_text("0", encoding="utf-8")
        self.mcp_delay.chmod(0o600)
        self.logs.append(log)
        script = Path(__file__).parents[1] / "integration" / "delayed_mcp_application.py"
        self.workers.append(
            subprocess.Popen(
                [
                    sys.executable,
                    str(script),
                    "--port",
                    str(private),
                    "--resource-url",
                    endpoint,
                    "--tool",
                    "words",
                    "--delay-file",
                    str(self.mcp_delay),
                ],
                env={
                    **os.environ,
                    "CIO_TEST_MCP_TOKEN": token,
                    "CIO_TEST_MCP_CALL_AUDIT": str(self.mcp_audit),
                    "CIO_TEST_MCP_RESULT_AUDIT": str(self.mcp_results),
                },
                cwd=self.directory,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        )
        self.start_proxy("mcp", origin, private)
        self.mcp_endpoint, self.mcp_token = endpoint, token

    def restart_mcp(self):
        previous = self.workers[-1]
        stop_process(previous)
        log = (self.directory / "mcp" / "service.log").open("ab")
        self.logs.append(log)
        self.workers.append(
            subprocess.Popen(
                previous.args,
                env={
                    **os.environ,
                    "CIO_TEST_MCP_TOKEN": self.mcp_token,
                    "CIO_TEST_MCP_CALL_AUDIT": str(self.mcp_audit),
                    "CIO_TEST_MCP_RESULT_AUDIT": str(self.mcp_results),
                },
                cwd=self.directory,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        )

    async def configure_mcp(self, config):
        await asyncio.to_thread(self.start_mcp)
        async with httpx.AsyncClient(verify=config.tls_context(), trust_env=False) as public:
            async with asyncio.timeout(25):
                while True:
                    try:
                        response = await public.get(self.mcp_endpoint)
                        if response.status_code in {502, 503}:
                            assert self.workers[0].poll() is None
                            await asyncio.sleep(0.1)
                            continue
                        assert response.status_code == 401
                        break
                    except (httpx.ConnectError, httpx.RemoteProtocolError):
                        assert self.workers[0].poll() is None
                        await asyncio.sleep(0.1)
        async with httpx2.AsyncClient(
            verify=config.tls_context(),
            trust_env=False,
            follow_redirects=False,
            timeout=20,
            headers={"Authorization": "Bearer " + self.mcp_token},
        ) as http:
            async with Client(
                streamable_http_client(self.mcp_endpoint, http_client=http)
            ) as client:
                tools = (await client.list_tools()).tools
                assert len(tools) == 1 and tools[0].name == "words"
                tool = tools[0]
        interface = {"name": tool.name, "input": tool.input_schema, "output": tool.output_schema}
        artifact = await asyncio.to_thread(
            config.artifacts().put,
            json.dumps(interface, sort_keys=True, separators=(",", ":")).encode(),
        )
        binding = Binding(
            id="words",
            revision="1",
            issuer="producer",
            registrar="producer",
            subject=Subject(id="documents.words", version="mcp-1", digest=artifact),
            scope=Scope(
                task="words",
                input_contract="words.in.v1",
                output_contract="words.out.v1",
                environment={"documents": "1"},
            ),
            target=Target(
                kind="mcp",
                name=tool.name,
                endpoint=self.mcp_endpoint,
                interface_digest=fingerprint(interface),
                implementation_identity="remote-unknown",
            ),
            input_schema=tool.input_schema,
            output_schema=tool.output_schema,
            callers=("producer", "receiver", "verifier"),
            verification_callers=("verifier",),
            effects="read-only",
        )
        from collective_intelligence_overlay.starter.adaptive_documents import write_json

        await asyncio.to_thread(
            write_json,
            config.private_key.parent / "application.json",
            {"counter": binding.model_dump(mode="json"), "counter_token": self.mcp_token},
        )

    def close(self):
        for process in (*self.workers, *self.proxies):
            stop_process(process)
        for log in self.logs:
            log.close()
        try:
            with self.admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                for name in self.names:
                    # These names are generated and tracked by this test only.
                    conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
                    conn.execute(text(f'DROP ROLE IF EXISTS "{name}"'))
        finally:
            self.admin.dispose()
