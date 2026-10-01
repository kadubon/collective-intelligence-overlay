import os
import secrets
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from collective_intelligence_overlay.application import load_application
from collective_intelligence_overlay.setup import bootstrap_database
from collective_intelligence_overlay.storage import Store


async def test_bootstrap_runtime_dml_without_ddl_and_production_readiness(
    app_config, identities, tmp_path
):
    operator_url = os.environ["CIO_TEST_DATABASE_URL"]
    name = "cio_production_" + uuid4().hex
    password = secrets.token_hex(16) + ":quote'\\end"
    runtime_url = make_url(operator_url).set(username=name, password=password, database=name)
    config = app_config.model_copy(
        update={"database_url": SecretStr(runtime_url.render_as_string(hide_password=False))}
    )
    admin = Store(operator_url, config.owner, {})
    host = None
    try:
        report = bootstrap_database(config, operator_url, Decimal(500))
        assert report["runtime_ddl"] is False
        assert password not in str(report)
        with pytest.raises(FileExistsError):
            bootstrap_database(config, operator_url, Decimal(500))
        host = load_application(config)
        assert host.overlay.store.capabilities()[0].issuer == config.owner
        with host.overlay.store.engine.connect() as conn:
            assert (
                conn.execute(text("SELECT remaining FROM budgets WHERE unit='work'")).scalar_one()
                == 500
            )
            assert (
                conn.execute(
                    text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
                ).scalar_one()
                is False
            )
        with pytest.raises(DBAPIError):
            with host.overlay.store.engine.begin() as conn:
                conn.execute(text("CREATE TABLE unauthorized_ddl(value integer)"))
        with pytest.raises(DBAPIError):
            with host.overlay.store.engine.begin() as conn:
                conn.execute(text("UPDATE alembic_version SET version_num='unverified'"))
        control = host.operations
        assert control is not None
        await control.start()
        assert control.state == "ready"
        assert (await control.handle(config.owner, {"operation": "status"}))["state"] == "ready"
        # Mutate only this test's protected copies, never the installed policy or OPA.
        policy = host.overlay.policy
        original_policy = policy.path.read_bytes()
        policy.path = tmp_path / "protected-policy.rego"
        policy.path.write_bytes(original_policy)
        original_key = config.private_key.read_bytes()
        original_binary = policy.binary
        for fault, expected_reason in (
            ("policy", "POLICY_CHANGED"),
            ("opa-unavailable", "DEPENDENCY_CHECK_FAILED"),
            ("different-key", "IDENTITY_CHANGED"),
            ("invalid-key", "DEPENDENCY_CHECK_FAILED"),
        ):
            if fault == "policy":
                policy.path.write_bytes(original_policy + b"\n# changed after startup\n")
            elif fault == "opa-unavailable":
                policy.binary = str(tmp_path / "absent-opa")
            elif fault == "different-key":
                config.private_key.write_bytes(identities["other"].signer.private_bytes)
            else:
                config.private_key.write_bytes(b"not a private key")
            status = await control.handle(config.owner, {"operation": "status"})
            assert status["state"] == "degraded" and status["reason"] == expected_reason
            invocation_id = "refused-" + fault
            refused = await control.handle(
                config.owner, {"operation": "invoke", "invocation_id": invocation_id}
            )
            assert refused["error"] == "SERVICE_INTAKE_CLOSED"
            assert host.executor.store.get(config.owner, invocation_id) is None
            with host.overlay.store.engine.connect() as conn:
                assert (
                    conn.execute(
                        text("SELECT remaining FROM budgets WHERE unit='work'")
                    ).scalar_one()
                    == 500
                )
            policy.path.write_bytes(original_policy)
            policy.binary = original_binary
            config.private_key.write_bytes(original_key)
            # Restoring dependencies alone does not reopen a degraded intake.
            assert control.state == "degraded"
            resumed = await control.handle(config.owner, {"operation": "resume"})
            assert resumed["state"] == "ready"
        assert config.private_key.read_bytes() == original_key
        assert policy.path.read_bytes() == original_policy
        await control.stop()
        host.close()
        host = None
    finally:
        if host is not None:
            if host.operations is not None:
                await host.operations.stop()
            host.close()
        # Delete only the exact new test-owned PostgreSQL names, never an operator DB.
        with admin.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            conn.execute(text(f'DROP ROLE IF EXISTS "{name}"'))
        admin.close()
