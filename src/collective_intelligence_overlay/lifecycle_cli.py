"""Explicit offline inspection/export and separately requested current assessment."""

from __future__ import annotations

import argparse
import asyncio
import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from securesystemslib.signer import Key  # type: ignore[attr-defined]

from .lifecycle import (
    CapabilityIdentity,
    CapabilityLifecycleView,
    ContributionObservation,
    GrowthObservation,
    HandoffObservation,
    HandoffRole,
    Residual,
    StockObservation,
    assess_stock,
    build_handoff,
    inspect_lifecycle,
    observe_contributions,
    observe_growth,
    snapshot_from_material,
)
from .models import RecordRef, UseRequest
from .security import Principal

MODELS = {
    model.__name__: model
    for model in (
        CapabilityLifecycleView,
        ContributionObservation,
        Residual,
        GrowthObservation,
        HandoffObservation,
        StockObservation,
    )
}


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "mode",
        choices=(
            "inspect",
            "contributions",
            "handoff",
            "growth",
            "assess",
            "export-originals",
            "schema",
            "tutorial",
        ),
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--fixture", action="store_true", help="bundled explicitly synthetic offline material"
    )
    source.add_argument(
        "--input", type=Path, help="explicit finite material JSON; no URL/path traversal"
    )
    source.add_argument("--config", type=Path, help="owner configuration for explicit Store access")
    parser.add_argument("--owner", help="host-selected owner for file material")
    parser.add_argument("--target", type=Path, help="exact CapabilityIdentity JSON")
    parser.add_argument(
        "--principals-file", type=Path, help="host-pinned public verification keys for DSSE input"
    )
    parser.add_argument("--page-size", type=int, default=128)
    parser.add_argument(
        "--cursor-file", type=Path, help="prior ObservationContext JSON with both cursors"
    )
    parser.add_argument("--opening", type=Path)
    parser.add_argument("--closing", type=Path)
    parser.add_argument("--requests-file", type=Path)
    parser.add_argument("--references-file", type=Path)
    parser.add_argument("--source-role", choices=tuple(HandoffRole), default="GENERATE")
    parser.add_argument("--target-role", choices=tuple(HandoffRole), default="VERIFY")
    parser.add_argument("--producer")
    parser.add_argument("--receiver")
    parser.add_argument("--contract", default="cio.lifecycle.view.v1")
    parser.add_argument("--type", choices=tuple(MODELS), default="CapabilityLifecycleView")
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--database-url")
    parser.add_argument("--opa")


def _file(path: Path | None) -> Any:
    if path is None:
        raise ValueError("required explicit JSON file missing")
    with path.open("rb") as stream:
        data = stream.read(1048577)
    if len(data) > 1048576:
        raise ValueError("lifecycle JSON byte bound exceeded")
    return json.loads(data)


def _pins(path: Path | None) -> dict[str, Principal]:
    if path is None:
        return {}
    values = _file(path)
    if not isinstance(values, dict) or len(values) > 64:
        raise ValueError("invalid finite public pin set")
    return {
        name: Principal(
            Key.from_dict(value["keyid"], value["key"]),
            value["trust_group"],
            frozenset(value.get("methods", ())),
            tuple(
                Key.from_dict(key["keyid"], key["key"]) for key in value.get("historical_keys", ())
            ),
            frozenset(value.get("compromised_keyids", ())),
        )
        for name, value in values.items()
    }


def _validate_mode(args: argparse.Namespace) -> None:
    read = {
        "fixture",
        "input",
        "config",
        "owner",
        "target",
        "principals_file",
        "page_size",
        "cursor_file",
        "receiver",
    }
    allowed = {
        "schema": {"type"},
        "tutorial": {"directory", "database_url", "opa"},
        "growth": {"opening", "closing", "input", "owner", "principals_file"},
        "assess": {"config", "requests_file"},
        "export-originals": {"config", "references_file"},
        "inspect": read,
        "contributions": read,
        "handoff": read | {"source_role", "target_role", "producer", "contract"},
    }[args.mode]
    defaults = {
        "page_size": 128,
        "source_role": "GENERATE",
        "target_role": "VERIFY",
        "type": "CapabilityLifecycleView",
        "contract": "cio.lifecycle.view.v1",
    }
    for key, value in vars(args).items():
        if key in {"command", "mode"} or key in allowed:
            continue
        if value not in (None, False) and value != defaults.get(key):
            raise ValueError("option is incompatible with lifecycle mode: " + key)
    if args.mode in {"assess", "export-originals"} and not args.config:
        raise ValueError("this lifecycle mode requires owner configuration")
    if args.fixture and (
        args.owner
        or args.target
        or args.principals_file
        or args.cursor_file
        or args.page_size != 128
    ):
        raise ValueError("fixture identity/material/bounds are fixed")
    if args.input and (args.cursor_file or args.page_size != 128):
        raise ValueError("file material is finite; Store pagination requires configuration")
    if args.config and (args.owner or args.principals_file):
        raise ValueError("configuration supplies the owner and public pins")
    if args.receiver and not args.config and args.mode != "handoff":
        raise ValueError("file/fixture receiver coordinates are part of the explicit material")
    if args.mode in {"inspect", "handoff"} and not args.fixture and not args.target:
        raise ValueError("inspection/handoff requires an exact target")


def run(args: argparse.Namespace) -> Any:
    _validate_mode(args)
    result = _run(args)
    if len(json.dumps(result).encode()) > 1048576:
        raise ValueError("lifecycle output byte bound exceeded")
    return result


def _run(args: argparse.Namespace) -> Any:
    if args.mode == "schema":
        return MODELS[args.type].model_json_schema()
    if args.mode == "tutorial":
        from .lifecycle_tutorial import run_tutorial

        if not args.directory or not args.database_url or not args.opa:
            raise ValueError(
                "actual-service tutorial needs directory, dedicated database URL and OPA"
            )
        return asyncio.run(run_tutorial(args.directory, args.database_url, args.opa))
    if args.mode == "growth":
        opening = StockObservation.model_validate(_file(args.opening))
        closing = StockObservation.model_validate(_file(args.closing))
        history = (
            snapshot_from_material(
                _file(args.input),
                owner=args.owner,
                caller=args.owner,
                principals=_pins(args.principals_file),
            )
            if args.input and args.owner
            else None
        )
        if args.input and not args.owner:
            raise ValueError("file history requires explicit owner")
        return observe_growth(opening, closing, history=history).model_dump(mode="json")
    if args.config:
        from .config import load_config
        from .lifecycle import ObservationContext
        from .lifecycle_store import export_originals, read_lifecycle_page

        config = load_config(args.config)
        identity, overlay = config.runtime()
        try:
            if args.mode == "assess":
                requests = _file(args.requests_file)
                if not isinstance(requests, list) or not 1 <= len(requests) <= 32:
                    raise ValueError("assessment needs 1 to 32 explicit requests")
                return asyncio.run(
                    assess_stock(overlay, tuple(UseRequest.model_validate(r) for r in requests))
                ).model_dump(mode="json")
            if args.mode == "export-originals":
                references = _file(args.references_file)
                if not isinstance(references, list) or not 1 <= len(references) <= 256:
                    raise ValueError("export needs finite exact references")
                return export_originals(
                    overlay.store,
                    tuple(RecordRef.model_validate(r) for r in references),
                    caller=identity.name,
                )
            target = CapabilityIdentity.model_validate(_file(args.target)) if args.target else None
            cursor = (
                ObservationContext.model_validate(_file(args.cursor_file))
                if args.cursor_file
                else None
            )
            snapshot = read_lifecycle_page(
                overlay.store,
                target,
                caller=identity.name,
                receiver=args.receiver,
                record_cursor=cursor.record_cursor if cursor else None,
                decision_cursor=cursor.decision_cursor if cursor else None,
                limit=args.page_size,
            )
        finally:
            overlay.store.close()
    elif args.fixture:
        fixture = json.loads(
            (
                files("collective_intelligence_overlay") / "fixtures/lifecycle-synthetic-v1.json"
            ).read_bytes()
        )
        if fixture["fixture_kind"] != "explicit_synthetic":
            raise ValueError("unexpected fixture provenance")
        target = CapabilityIdentity.model_validate(fixture["target"])
        snapshot = snapshot_from_material(fixture["material"], owner="receiver", caller="receiver")
    elif args.input:
        if not args.owner:
            raise ValueError("explicit file input requires host owner")
        target = CapabilityIdentity.model_validate(_file(args.target)) if args.target else None
        snapshot = snapshot_from_material(
            _file(args.input),
            owner=args.owner,
            caller=args.owner,
            principals=_pins(args.principals_file),
        )
    else:
        raise ValueError("select explicit fixture, input material or owner config")
    if args.mode == "contributions":
        return {
            "context": snapshot.context.model_dump(mode="json"),
            "observations": [c.model_dump(mode="json") for c in observe_contributions(snapshot)],
        }
    if target is None:
        raise ValueError("this lifecycle mode requires an exact target")
    view = inspect_lifecycle(snapshot, target)
    if args.mode == "inspect":
        return view.model_dump(mode="json")
    if args.mode == "handoff":
        return build_handoff(
            view,
            source_role=HandoffRole(args.source_role),
            target_role=HandoffRole(args.target_role),
            producer=args.producer or target.issuer,
            receiver=args.receiver or snapshot.context.owner,
            contract_identity=args.contract,
        ).model_dump(mode="json")
    raise ValueError("this mode requires explicit owner configuration")
