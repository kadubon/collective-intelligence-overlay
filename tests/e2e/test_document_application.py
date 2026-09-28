import asyncio
import json
import os
import sys
from pathlib import Path

import pytest


async def test_external_document_application_three_process_formation_restart_and_withdrawal(
    tmp_path, policy
):
    if not os.environ.get("CIO_TEST_DATABASE_URL"):
        pytest.skip("real PostgreSQL required")
    script = Path(__file__).parents[2] / "examples" / "document_application.py"
    directory = tmp_path / "documents"
    opa = await asyncio.to_thread(os.path.abspath, policy.binary)
    # Execute the installed application file from outside the repository directory.
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(script),
        "--directory",
        str(directory),
        cwd=tmp_path,
        env={**os.environ, "CIO_OPA": opa},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 280)
    except BaseException:
        if process.returncode is None:
            process.terminate()
            await process.wait()
        raise
    assert process.returncode == 0, stderr.decode(errors="replace")
    result = json.loads(stdout)
    assert result["processes"] == len(set(result["pids"].values())) == 3
    assert result["restarted_receiver_pid"] != result["pids"]["receiver"]
    assert result["before_verification"] == "unknown"
    assert result["ungranted_probe"] == "rejected"
    assert result["c1_check"] == result["c4_check"] == "PASS"
    assert len(result["formation_c3"]["formation"]["receipts"]) == 2
    assert len(result["formation_c4"]["formation"]["receipts"]) == 3
    assert result["formation_c4"]["outcome"] == "UNKNOWN"
    assert result["held_out_result"] == {"long": True, "threshold": 2}
    assert result["accepted_before"] == result["checked_after"] == 2
    assert result["accepted_after"] == 0
    assert result["after_withdrawal"] == ["REJECT", "REJECT"]
    assert result["delta"]["complete"]
    assert sum(len(page["lineage"]) for page in result["metrics_pages"]) == 2
