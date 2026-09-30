import json
import subprocess
import sys

from collective_intelligence_overlay.config import Config, TrustedIdentity


def test_native_service_logger_redacts_library_errors_and_rotates(tmp_path, identities):
    identity = identities["receiver"]
    secret = "Bearer-private-token-and-raw-business-document"
    config = Config(
        owner="receiver",
        database_url="postgresql+pg8000://private-dsn:secret@localhost/test",
        private_key=tmp_path / "identity.pem",
        artifact_directory=tmp_path / "artifacts",
        opa_binary="explicit-opa",
        url="https://receiver.example.test/",
        identities={
            "receiver": TrustedIdentity(
                keyid=identity.signer.public_key.keyid,
                key=identity.signer.public_key.to_dict(),
                trust_group="receiver",
            )
        },
        log_directory=tmp_path / "logs",
        log_segment_bytes=4096,
        log_backup_segments=2,
    )
    path = tmp_path / "config.json"
    data = config.model_dump(mode="json")
    data["database_url"] = config.database_url.get_secret_value()
    path.write_text(json.dumps(data))
    script = """
import json, logging, sys
from pathlib import Path
from collective_intelligence_overlay.config import load_config
from collective_intelligence_overlay.observability import configure_logging
config = load_config(Path(sys.argv[1]))
handler = configure_logging(config)
for index in range(100):
    logging.getLogger('collective_intelligence_overlay.operations').info(json.dumps({
        'owner': config.owner, 'reason': 'REQUEST_FINISHED', 'elapsed_seconds': index / 100,
        'correlation': 'a' * 16, 'request_body': sys.argv[2]}))
try:
    raise RuntimeError(sys.argv[2] + config.database_url.get_secret_value())
except RuntimeError:
    logging.getLogger('mcp').exception(sys.argv[2])
logging.getLogger(sys.argv[2]).error(sys.argv[2])
handler.close()
"""
    subprocess.run(
        [sys.executable, "-c", script, str(path), secret],
        check=True,
        capture_output=True,
        timeout=15,
    )
    files = list(config.log_directory.glob("owner.jsonl*"))
    assert len(files) == 3
    assert all(p.stat().st_size <= 4096 for p in files)
    content = "\n".join(p.read_text() for p in files)
    assert secret not in content and config.database_url.get_secret_value() not in content
    rows = [json.loads(line) for line in content.splitlines() if line]
    assert any(row.get("exception_type") == "RuntimeError" for row in rows)
    assert any(row["reason"] == "REQUEST_FINISHED" for row in rows)
