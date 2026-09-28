import os
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url

from collective_intelligence_overlay.demo import initialize
from collective_intelligence_overlay.storage import budgets


def test_fresh_experiment_owners_have_separate_keys_databases_and_allowances(tmp_path, policy):
    url = os.environ.get("CIO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("real PostgreSQL required")
    assignments = {"producer": Decimal(50), "receiver": Decimal(50), "verifier": Decimal(14)}
    first = initialize(tmp_path / "first", url, policy.binary, work_allowances=assignments)
    second = initialize(tmp_path / "second", url, policy.binary, work_allowances=assignments)
    assert {
        make_url(c.database_url.get_secret_value()).database for c in first.values()
    }.isdisjoint(make_url(c.database_url.get_secret_value()).database for c in second.values())
    assert {v.keyid for v in first["receiver"].identities.values()}.isdisjoint(
        v.keyid for v in second["receiver"].identities.values()
    )
    for arm in (first, second):
        for owner, config in arm.items():
            _, overlay = config.runtime()
            try:
                with overlay.store.engine.connect() as conn:
                    assert (
                        conn.execute(select(budgets.c.remaining)).scalar_one() == assignments[owner]
                    )
            finally:
                overlay.store.close()
    _, changed = first["receiver"].runtime()
    try:
        changed.store.acquire("only-first-arm", "receiver", "work", Decimal(1))
    finally:
        changed.store.close()
    _, unaffected = second["receiver"].runtime()
    try:
        with unaffected.store.engine.connect() as conn:
            assert conn.execute(select(budgets.c.remaining)).scalar_one() == 50
    finally:
        unaffected.store.close()


def test_invalid_initial_allowances_do_not_create_experiment_directory(tmp_path):
    for values in (
        {"unknown-owner": Decimal(1)},
        {"verifier": Decimal("NaN")},
        {"receiver": Decimal(-1)},
    ):
        with pytest.raises(ValueError, match="per-owner"):
            initialize(tmp_path / "invalid", "unused", "unused", work_allowances=values)
        assert not (tmp_path / "invalid").exists()


async def test_existing_experiment_arm_is_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "examples"))
    from evaluate_documents import run_arm

    marker = tmp_path / "result.json"
    marker.write_text("original result", encoding="utf-8")
    with pytest.raises(FileExistsError):
        await run_arm(tmp_path, "unused", "unused", "static-run", "baseline")
    assert marker.read_text(encoding="utf-8") == "original result"


def test_saved_comparison_signatures_conservation_and_tampered_counts(tmp_path, monkeypatch):
    import json
    import zipfile

    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "examples"))
    from evaluate_documents import validate_results

    archive_path = Path(__file__).parents[2] / "experiments" / "documents-pilot-2.zip"
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.namelist():
            assert (tmp_path / member).resolve().is_relative_to(tmp_path.resolve())
        archive.extractall(tmp_path)
    checked = validate_results(tmp_path)
    assert checked["arms"] == 4 and checked["separate_databases"] == 12
    assert checked["verified_signed_records"] == 550
    path = tmp_path / "arm-0" / "receiver-observations.json"
    original = path.read_text(encoding="utf-8")
    report = json.loads(original)
    report["remaining"]["work"] = str(Decimal(report["remaining"]["work"]) + 1)
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="conservation"):
        validate_results(tmp_path)
    path.write_text(original, encoding="utf-8")
    result_path = tmp_path / "results.json"
    results = json.loads(result_path.read_text(encoding="utf-8"))
    results["arms"][1]["passed_business_tasks"] += 1
    result_path.write_text(json.dumps(results), encoding="utf-8")
    with pytest.raises(ValueError, match="outcome counts"):
        validate_results(tmp_path)
