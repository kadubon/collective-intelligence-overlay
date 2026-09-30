import copy
import json
from pathlib import Path

import pytest


def test_prepublication_does_not_require_already_published_results(monkeypatch):
    root = Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    from production_acceptance import POST_PUBLICATION, require_prepublication

    actual = json.loads((root / "docs/production-040-acceptance.json").read_text())
    with pytest.raises(AssertionError):
        require_prepublication(actual)
    prepared = copy.deepcopy(actual)
    for row in prepared["requirements"]:
        row.update(status="verified", observed="fixture completed", remaining=[])
        if row["id"] in POST_PUBLICATION:
            row.update(
                status="verified prepublication", remaining=sorted(POST_PUBLICATION[row["id"]])
            )
    require_prepublication(prepared)
    declared_soak = copy.deepcopy(prepared)
    next(row for row in declared_soak["requirements"] if row["id"] == "P24")["status"] = "declared"
    with pytest.raises(AssertionError):
        require_prepublication(declared_soak)
    # A completed release path cannot excuse a missing native fault or soak gate.
    for missing in ("P07", "P15", "P24", "P25", "P29", "P30", "P31", "P32"):
        incomplete = copy.deepcopy(prepared)
        row = next(row for row in incomplete["requirements"] if row["id"] == missing)
        row["remaining"].append("required operating validation")
        with pytest.raises(AssertionError):
            require_prepublication(incomplete)
    duplicate = copy.deepcopy(prepared)
    duplicate["requirements"][-1] = duplicate["requirements"][-2]
    with pytest.raises(AssertionError):
        require_prepublication(duplicate)
