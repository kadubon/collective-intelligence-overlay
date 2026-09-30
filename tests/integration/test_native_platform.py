"""Real native paths, process restart, sockets and TLS verification on every runner."""

import os
import socket
import ssl
import subprocess
import sys
import threading
import time
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from process_control import stop_owned_process

from collective_intelligence_overlay.artifacts import Artifacts
from collective_intelligence_overlay.models import now
from collective_intelligence_overlay.opa_install import verify_opa


def test_native_opa_and_unicode_spaces_atomic_replace_modes_and_symlinks(policy, tmp_path):
    source = Path(os.environ["CIO_OPA"])
    assert "Version: 1.21.0" in verify_opa(source)
    root = tmp_path / "日本語 空白 e\u0301"
    artifacts = Artifacts(root)
    value = "改行\r\nline\n".encode()
    name = artifacts.put(value)
    assert artifacts.get(name) == value
    temporary = root / "replacement"
    temporary.write_bytes(value)
    os.replace(temporary, root / name)
    assert artifacts.get(name) == value and not temporary.exists()
    # Both case-sensitive and default case-insensitive APFS must preserve the byte identity.
    probe = root / "CaseProbe"
    probe.write_bytes(b"case")
    if (root / "caseprobe").exists():
        assert (root / "caseprobe").read_bytes() == b"case"
    if os.name != "nt":
        assert root.stat().st_mode & 0o777 == 0o700
        (root / name).unlink()
        (root / name).symlink_to(probe)
        with pytest.raises(ValueError, match="unsafe"):
            artifacts.get(name)
        with pytest.raises(ValueError, match="symlink"):
            artifacts.put(value)


def test_native_subprocess_termination_restart_and_port_reuse(tmp_path):
    with socket.socket() as free:
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
    home = tmp_path / "実 process directory"
    home.mkdir()
    script = """
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'owned process')
    def log_message(self, *args): pass
ThreadingHTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
"""
    for _ in range(2):
        process = subprocess.Popen(
            [sys.executable, "-c", script, str(port)],
            cwd=home,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 10
            with httpx.Client(trust_env=False, timeout=1) as client:
                while True:
                    try:
                        response = client.get(f"http://127.0.0.1:{port}")
                        assert response.text == "owned process"
                        break
                    except httpx.TransportError:
                        assert process.poll() is None and time.monotonic() < deadline
                        time.sleep(0.02)
        finally:
            stop_owned_process(process)
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_native_certificate_store_rejects_untrusted_and_wrong_hostname(tmp_path):
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
    certificate_path, key_path = tmp_path / "certificate.pem", tmp_path / "private.pem"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"verified local fixture")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate_path, key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with httpx.Client(trust_env=False, timeout=3) as client:
            with pytest.raises(httpx.ConnectError):
                client.get(f"https://localhost:{port}")
        trusted = ssl.create_default_context(cafile=str(certificate_path))
        with httpx.Client(verify=trusted, trust_env=False, timeout=3) as client:
            assert client.get(f"https://localhost:{port}").text == "verified local fixture"
            with pytest.raises(httpx.ConnectError):
                client.get(f"https://127.0.0.1:{port}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert not thread.is_alive()
