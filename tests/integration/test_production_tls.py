import asyncio
import json
import os
import secrets
import subprocess
import sys
import tempfile
from datetime import timedelta
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from process_control import stop_owned_process
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url

from collective_intelligence_overlay.adapters.a2a import EXTENSION, extension_data, send
from collective_intelligence_overlay.config import Peer
from collective_intelligence_overlay.demo import free_port
from collective_intelligence_overlay.models import now
from collective_intelligence_overlay.setup import bootstrap_database
from collective_intelligence_overlay.storage import Store


def tls_fixture(directory):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now() - timedelta(minutes=1))
        .not_valid_after(now() + timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = directory / "certificate.pem", directory / "tls-private.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


@pytest.mark.parametrize("separate_operator", [False, True])
async def test_actual_caddy_https_application_drain_and_process_restart(
    app_config, tmp_path, identities, separate_operator
):
    executable = os.environ.get("CIO_CADDY")
    if executable is None:
        pytest.skip("CIO_CADDY required: actual production reverse-proxy test not run")
    caddy = await asyncio.to_thread(Path(executable).resolve)
    version = await asyncio.to_thread(
        subprocess.run,
        [str(caddy), "version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert version.stdout.strip() == "v2.11.4+cio.1"
    public_port, private_port = free_port(), free_port()
    endpoint = f"https://localhost:{public_port}/"
    cert, key = tls_fixture(tmp_path)
    operator_url = os.environ["CIO_TEST_DATABASE_URL"]
    db = "cio_tls_" + uuid4().hex
    runtime_url = make_url(operator_url).set(
        username=db, password=secrets.token_hex(24), database=db
    )
    config = app_config.model_copy(
        update={
            "database_url": SecretStr(runtime_url.render_as_string(hide_password=False)),
            "url": endpoint,
            "listen_port": private_port,
            "tls_ca_certificate": cert,
            "peers": (Peer(identity=app_config.owner, url=endpoint),),
            "operator_callers": ("other",) if separate_operator else (),
        }
    )
    config_path = tmp_path / "config.json"
    data = config.model_dump(mode="json")
    data["database_url"] = config.database_url.get_secret_value()
    config_path.write_text(json.dumps(data))
    control_key = tmp_path / "operator.pem"
    control_key.write_bytes(identities["other"].signer.private_bytes)
    client_path = tmp_path / "control-client.json"
    client_data = {**data, "private_key": str(tmp_path / "absent-owner-key.pem")}
    client_path.write_text(json.dumps(client_data))

    async def control_cli(operation, caller, pem, expected):
        completed = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                "-m",
                "collective_intelligence_overlay.cli",
                operation,
                "--config",
                str(client_path),
                "--identity-name",
                caller,
                "--identity-private-key",
                str(pem),
            ],
            cwd=tmp_path,
            capture_output=True,
            timeout=40,
            env=os.environ.copy(),
        )
        assert completed.returncode == expected, completed.stderr.decode(errors="replace")
        response = json.loads(completed.stdout or completed.stderr)
        if expected == 2:
            assert response["error"] == "InternalError"
        return response

    caddy_path = tmp_path / "Caddyfile"
    caddy_path.write_bytes(
        (files("collective_intelligence_overlay") / "starter/Caddyfile").read_bytes()
    )
    proxy_env = {
        **os.environ,
        "CIO_PUBLIC_ADDRESS": endpoint.rstrip("/"),
        "CIO_LISTEN_PORT": str(private_port),
        "CIO_TLS_CERTIFICATE": str(cert),
        "CIO_TLS_PRIVATE_KEY": str(key),
    }
    admin = Store(operator_url, config.owner, {})
    processes, logs = [], []
    overlay = None

    def start_peer():
        log = tempfile.TemporaryFile()
        logs.append(log)
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "collective_intelligence_overlay.cli",
                "peer",
                "--config",
                str(config_path),
            ],
            cwd=tmp_path,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )
        processes.append(process)
        return process

    try:
        from decimal import Decimal

        bootstrap_database(config, operator_url, Decimal(500))
        identity, overlay = config.runtime()
        peer = await asyncio.to_thread(start_peer)
        log = tempfile.TemporaryFile()
        logs.append(log)
        validate = await asyncio.to_thread(
            subprocess.run,
            [str(caddy), "validate", "--config", str(caddy_path)],
            env=proxy_env,
            capture_output=True,
            timeout=10,
        )
        assert validate.returncode == 0, validate.stderr.decode(errors="replace")
        processes.append(
            await asyncio.to_thread(
                subprocess.Popen,
                [str(caddy), "run", "--config", str(caddy_path)],
                cwd=tmp_path,
                env=proxy_env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        )

        async def wait_ready():
            async with asyncio.timeout(30):
                while True:
                    try:
                        status = await send(config, identity, config.owner, {"operation": "status"})
                        if status["state"] == "ready":
                            return
                    except Exception:
                        pass
                    assert all(process.poll() is None for process in processes)
                    await asyncio.sleep(0.05)

        await wait_ready()
        timestamp = now()
        token = jwt.encode(
            {
                "iss": config.owner,
                "sub": config.owner,
                "aud": endpoint,
                "iat": timestamp,
                "exp": timestamp + timedelta(seconds=60),
            },
            identity.signer.private_bytes,
            algorithm="EdDSA",
        )
        from a2a.types import Message, Part, Role, SendMessageRequest
        from google.protobuf.json_format import MessageToDict

        message = SendMessageRequest(
            message=Message(
                message_id="fragmented-status",
                role=Role.ROLE_USER,
                parts=[Part(data=extension_data({"operation": "status"}))],
                extensions=[EXTENSION],
            )
        )
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "fragmented-status",
                "method": "SendMessage",
                "params": MessageToDict(message),
            }
        ).encode()

        async def fragmented(value):
            for start in range(0, len(value), 64):
                yield value[start : start + 64]

        async with httpx.AsyncClient(
            verify=config.tls_context(),
            trust_env=False,
            headers={
                "Authorization": "Bearer " + token,
                "A2A-Extensions": EXTENSION,
                "A2A-Version": "1.0",
            },
        ) as authenticated:
            streamed = await authenticated.post(
                endpoint, content=fragmented(body), headers={"Content-Type": "application/json"}
            )
            assert streamed.status_code == 200 and "DEPENDENCIES_READY" in streamed.text
            oversized = await authenticated.post(endpoint, content=b"x" * 262145)
            assert oversized.status_code == 413
            streaming_oversized = await authenticated.post(
                endpoint, content=fragmented(b"x" * 262145)
            )
            assert streaming_oversized.status_code == 413
        async with httpx.AsyncClient(verify=config.tls_context(), trust_env=False) as public:
            response = await public.get(endpoint)
            assert response.status_code in {400, 401, 403}
            assert config.owner not in response.text
            assert config.database_url.get_secret_value() not in response.text
        async with httpx.AsyncClient(trust_env=False) as untrusted:
            with pytest.raises(httpx.ConnectError):
                await untrusted.get(endpoint)
        async with httpx.AsyncClient(verify=config.tls_context(), trust_env=False) as wrong_host:
            with pytest.raises(httpx.ConnectError):
                await wrong_host.get(f"https://127.0.0.1:{public_port}/")
        candidate = overlay.store.capabilities()[0]
        request = {
            "operation": "invoke",
            "invocation_id": "tls-original-probe",
            "binding_id": "word-count",
            "binding_digest": candidate.binding_digest,
            "arguments": {"text": "owner 文書 proof"},
            "purpose": "verification",
        }
        result = await send(config, identity, config.owner, request)
        assert result["state"] == "completed" and result["result"] == {"words": 3}
        telemetry = await send(config, identity, config.owner, {"operation": "operational_metrics"})
        assert telemetry["database"]["invocation_states"]["completed"] == 1
        assert telemetry["database"]["measured_consumption_from_allowance"] is False
        assert telemetry["artifacts"]["capacity_bytes"] == 268435456
        owner_logs = list((config.private_key.parent / "logs").glob("owner.jsonl*"))
        assert owner_logs
        logged = "\n".join(p.read_text() for p in owner_logs)
        assert token not in logged and config.database_url.get_secret_value() not in logged
        assert request["arguments"]["text"] not in logged
        assert overlay.store.evidence() == []
        if separate_operator:
            assert (await control_cli("status", "other", control_key, 0))["state"] == "ready"
            await control_cli("drain", config.owner, config.private_key, 2)
            assert (await send(config, identity, config.owner, {"operation": "status"}))[
                "state"
            ] == "ready"
            ungranted = await send(
                config,
                identities["other"],
                config.owner,
                {**request, "invocation_id": "operator-ungranted-probe"},
            )
            assert ungranted["state"] == "rejected"
            assert (await control_cli("drain", "other", control_key, 0))["state"] == "draining"
            await control_cli("resume", config.owner, config.private_key, 2)
            assert (await send(config, identities["other"], config.owner, {"operation": "resume"}))[
                "state"
            ] == "ready"
            assert (await send(config, identities["other"], config.owner, {"operation": "drain"}))[
                "state"
            ] == "draining"
        else:
            assert (await send(config, identity, config.owner, {"operation": "drain"}))[
                "state"
            ] == "draining"
        denied = await send(
            config, identity, config.owner, {**request, "invocation_id": "drained-new"}
        )
        assert denied["error"] == "SERVICE_INTAKE_CLOSED"
        query = {"operation": "invocation", "invocation_id": "tls-original-probe"}
        assert (await send(config, identity, config.owner, query))["invocation"] == result
        await asyncio.to_thread(stop_owned_process, peer)
        processes.remove(peer)
        await asyncio.to_thread(start_peer)
        await wait_ready()
        assert (await send(config, identity, config.owner, query))["invocation"] == result
        assert await send(config, identity, config.owner, request) == result
        assert overlay.store.capabilities() == [candidate]
    finally:
        for process in reversed(processes):
            await asyncio.to_thread(stop_owned_process, process)
        for log in logs:
            log.close()
        if overlay is not None:
            overlay.store.close()
        with admin.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
            conn.execute(text(f'DROP ROLE IF EXISTS "{db}"'))
        admin.close()
