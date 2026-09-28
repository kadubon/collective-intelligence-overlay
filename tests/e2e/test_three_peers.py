import os

import pytest

from collective_intelligence_overlay.demo import initialize, run_demo


async def test_three_process_lifecycle(tmp_path, policy):
    url = os.environ.get("CIO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("real PostgreSQL required")
    directory = tmp_path / "demo"
    configs = initialize(directory, url, policy.binary)
    result = await run_demo(directory, configs)
    assert result["processes"] == 3
    assert result["admission"] == "ACCEPT"
    assert result["held_out_result"] == "<p>Rows: 3; total: 117.00</p>"
    assert result["changed_environment"] == "REQUALIFY"
    assert result["after_dependency_revocation"] == "REJECT"
