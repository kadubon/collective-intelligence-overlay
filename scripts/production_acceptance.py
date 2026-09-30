"""Prepublication register gate; publication results cannot precede publication."""

from typing import Any

# These are the only facts which inherently need the already published artifact.
POST_PUBLICATION = {
    "P31": {"publish", "post-publication verification"},
    "P32": {"final actual results"},
}


def require_prepublication(acceptance: dict[str, Any]) -> None:
    rows = acceptance["requirements"]
    assert len(rows) == 32 and {row["id"] for row in rows} == {f"P{i:02}" for i in range(1, 33)}, (
        "missing, changed or duplicate production requirements"
    )
    for row in rows:
        allowed = {"verified"}
        if row["id"] == "P01":
            allowed.add("verified baseline")
        if row["id"] == "P02":
            allowed.add("declared")
        if row["status"] in allowed:
            assert row["observed"] is not None and not row["remaining"], row["id"]
            continue
        assert (
            row["id"] in POST_PUBLICATION
            and row["status"] == "verified prepublication"
            and row["observed"] is not None
            and set(row["remaining"]) == POST_PUBLICATION[row["id"]]
            and len(row["remaining"]) == len(POST_PUBLICATION[row["id"]])
        ), f"{row['id']} is not accepted; publication remains closed"
