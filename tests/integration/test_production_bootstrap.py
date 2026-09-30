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


async def test_bootstrap_runtime_dml_without_ddl_and_production_readiness(app_config):
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
