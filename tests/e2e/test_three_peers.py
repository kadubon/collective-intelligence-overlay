import os

import pytest

from collective_intelligence_overlay.demo import initialize, run_demo


async def test_three_process_lifecycle(tmp_path, policy, monkeypatch):
    from a2a.client import AgentCardResolutionError

    from collective_intelligence_overlay.adapters import a2a

    actual = a2a.send
    unavailable = {"producer", "verifier", "receiver"}

    async def delayed(config, identity, peer_name, data):
        if peer_name in unavailable:
            unavailable.remove(peer_name)
            raise AgentCardResolutionError("server not yet ready")
        if data.get("operation") == "sync":
            data = {**data, "page_size": 1}
        return await actual(config, identity, peer_name, data)

    monkeypatch.setattr(a2a, "send", delayed)
    url = os.environ.get("CIO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("real PostgreSQL required")
    directory = tmp_path / "demo"
    configs = initialize(directory, url, policy.binary)
    result = await run_demo(directory, configs)
    assert result["processes"] == 3
    assert len(result["comparison"]) == 4
    assert all(r["correct"] == r["tasks"] == 3 for r in result["comparison"])
    assert result["admission"] == "ACCEPT"
    assert result["held_out_result"] == "<p>Rows: 3; total: 117.00</p>"
    assert result["changed_environment"] == "REQUALIFY"
    assert result["after_dependency_revocation"] == "REJECT"
    assert result["metrics"]["actions"]["import"] >= 6
