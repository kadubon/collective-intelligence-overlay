"""Finite candidate witnesses, strict wire, directional gates and phase attribution."""

import json
import sys
from contextvars import ContextVar
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import httpx
import pytest
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from accumulation_primitives import bounded_execute, factory  # noqa: E402
from accumulation_session import CappedSession, SharedCap, StudySession  # noqa: E402
from accumulation_tasks import compare  # noqa: E402
from bounded_scratch_application import (  # noqa: E402
    compile_slots,
    model_prompt,
    slot_candidates,
    wire_schema,
)
from bounded_scratch_protocol import controls, locked_gate, screen_decision  # noqa: E402
from bounded_scratch_tasks import World, semantic_rule_baseline  # noqa: E402
from check_gemma_transport import validate_wire  # noqa: E402


@pytest.mark.parametrize("seed", [944101, 944208, 944403])
async def test_all_allowed_candidates_execute_and_have_unique_hidden_results(seed):
    w = World(seed, "nonmodel-unit")
    for family in ("sql", "composition"):
        for level in ("L0", "L1", "L2"):
            public, hidden = (w.problem(family, level, split) for split in ("public", "hidden"))
            values = []
            successes = []
            for candidate in slot_candidates(family, public.difficulty):
                solution = compile_slots(public, candidate)
                actual = await bounded_execute(solution, hidden)
                assert "rows" in actual and actual["rows"]
                values.append(json.dumps(actual, sort_keys=True))
                successes.append(compare(actual, w.expected(hidden)))
                # New factory closure reconstructs from persisted public parameters.
                restored = factory(json.loads(json.dumps(solution.model_dump(mode="json"))))
                assert await restored({"problem": hidden.model_dump(mode="json")}) == actual
            assert len(set(values)) == len(values) == 2 ** (int(level[-1]) + 1)
            assert sum(successes) == 1
            assert compare(await bounded_execute(w.oracle(public), hidden), w.expected(hidden))
            assert compare(
                await bounded_execute(
                    compile_slots(public, semantic_rule_baseline(public)), hidden
                ),
                w.expected(hidden),
            )


@pytest.mark.parametrize(
    "extra",
    [
        {"uses": ["made-up"]},
        {"sql": "DROP TABLE readings"},
        {"coefficients": [9, 9, 9]},
        {"source_id": "invisible"},
    ],
)
def test_model_cannot_supply_execution_fields_or_invisible_references(extra):
    problem = World(1, "unit").problem("sql", "L1", "public")
    good = {"negative_policy": "include", "null_policy": "zero"}
    with pytest.raises(ValidationError):
        compile_slots(problem, {**good, **extra})
    with pytest.raises(ValidationError):
        compile_slots(problem, {"negative_policy": "approximately_include", "null_policy": "zero"})
    with pytest.raises(ValidationError):
        compile_slots(problem, {"negative_policy": "include"})


def test_public_prompt_no_oracle_ids_arm_or_contract_and_external_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    w = World(944208, "locked-validation")
    for family in ("sql", "composition"):
        p = w.problem(family, "L2", "public")
        text = model_prompt(p, ())
        assert w.id not in text and p.id not in text and p.contract not in text
        payload = json.loads(text.split("\n", 1)[1])
        assert not {"expected", "arm", "seed", "stage"} & payload["problem"].keys()
        candidates = payload["candidate_meanings"]
        assert {json.dumps(x["values"], sort_keys=True) for x in candidates} == {
            json.dumps(x, sort_keys=True) for x in slot_candidates(family, p.difficulty)
        }
        assert "tasks" not in (ROOT / "scripts/bounded_scratch_application.py").read_text()
    positions = set()
    for seed in range(50):
        w = World(seed, "leakage-unit")
        p = w.problem("sql", "L2", "public")
        shown = json.loads(model_prompt(p, ()).split("\n", 1)[1])["candidate_meanings"]
        positions.add(next(i for i, c in enumerate(shown) if c["values"] == w.slots("sql", "L2")))
    assert positions == set(range(8))


def rows(k, n=8):
    return [
        {"succeeded": i < k, "normal": True, "schema": True, "executable": True} for i in range(n)
    ]


def test_directional_screen_never_selects_floor_ceiling_or_pools_families():
    assert screen_decision(rows(0), "L1", ["L1"])["next"] == "L0"
    assert screen_decision(rows(8), "L1", ["L1"])["next"] == "L2"
    assert screen_decision(rows(0), "L0", ["L1", "L0"])["selected"] is None
    assert screen_decision(rows(8), "L2", ["L1", "L2"])["selected"] is None
    assert screen_decision(rows(4), "L1", ["L1"])["selected"] == "L1"
    assert screen_decision(rows(4, 7), "L1", ["L1"])["next"] is None


def test_locked_requires_both_mixed_blocks_and_all_interfaces_and_controls():
    selected = {"sql": "L1", "composition": "L1"}
    control = {
        f: {
            "functional_classes": 4,
            "uniform_random": {"rate": 0.25},
            "best_constant": {"rate": 0.3},
        }
        for f in selected
    }
    data = [
        {**r, "family": f, "block": i // 6} for f in selected for i, r in enumerate(rows(6, 12))
    ]
    assert not locked_gate(data, selected, control, stock_ready=True)["confirmation_authorized"]
    data = [{**r, "family": f, "block": b} for f in selected for b in (0, 1) for r in rows(3, 6)]
    assert locked_gate(data, selected, control, stock_ready=True)["confirmation_authorized"]
    control["sql"]["functional_classes"] = 2
    assert (
        locked_gate(data, selected, control, stock_ready=True)["status"]
        == "chance_dominated_or_unresolved"
    )
    data[0]["schema"] = False
    assert locked_gate(data, selected, control, stock_ready=True)["status"] == "assay_not_ready"


async def test_nonlearning_controls_are_separate_and_public_rule_is_preserved():
    value = await controls("sql", "L1", list(range(944500, 944516)))
    assert value["functional_classes"] == 4 and value["semantic_rule"]["passed"] == 16
    assert value["classification"] == "nonlearning_control_not_model_inference"


@pytest.mark.parametrize("family", ["sql", "composition"])
@pytest.mark.parametrize("level", ["L0", "L1", "L2"])
async def test_public_sdk_delivers_each_exact_native_format(family, level):
    """Synthetic HTTP response; real public SDK serialization, not model inference."""
    from agent_framework import Message

    from collective_intelligence_overlay.adapters.ollama import local_ollama_client

    p = World(1, "wire-unit").problem(family, level, "public")
    draft = wire_schema(p)
    fields = slot_candidates(family, p.difficulty)[0]
    seen = []

    async def respond(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200,
            json={
                "model": "gemma4:e4b",
                "done": True,
                "message": {"role": "assistant", "content": json.dumps(fields)},
                "prompt_eval_count": 20,
                "eval_count": 10,
            },
        )

    async with local_ollama_client(
        "http://127.0.0.1:11444",
        model="gemma4:e4b",
        seconds=5,
        transport=httpx.MockTransport(respond),
    ) as client:
        response = await client.get_response(
            [Message(role="user", contents=[model_prompt(p, ())])],
            options={
                "response_format": draft,
                "think": False,
                "options": {"num_ctx": 4096, "num_predict": 256, "draft_num_predict": 0},
            },
        )
    assert seen[0]["format"] == draft.model_json_schema()
    assert validate_wire(response.text, seen[0]["format"], draft).model_dump() == fields


async def test_phase_metadata_and_offer_are_observational_not_rpc_authority(monkeypatch, tmp_path):
    import production_session

    sent = []

    async def fake_send(config, identity, destination, data):
        sent.append(data)
        return {"state": "completed"}

    monkeypatch.setattr(production_session, "send", fake_send)
    session = CappedSession(tmp_path, tmp_path, "unused", "unused", "unused", 100, "unused")
    session.configs["p"], session.identities["p"] = "config", "identity"
    study = StudySession.__new__(StudySession)
    study.protocol, study.world = {"phase_recording": "explicit-v1"}, SimpleNamespace(stage="unit")
    study.phase_intervals = []
    study.observation_context = ContextVar(
        "unit-phase", default=MappingProxyType({"phase": "setup"})
    )
    study.cap = SharedCap(
        {"model_calls": 10, "model_tokens": 40000, "wall_seconds": 20, "application_actions": 100},
        context=4096,
        predict=256,
    )
    study.checks = {"offered": [1, 2]}
    session.study = study
    with study.observe_phase("probe", offer="offered", cost_scope="online"):
        await session.call("p", operation="app.check", offer="offered")
        with study.observe_phase("import"):
            await session.call("p", operation="app.import")
    assert [c["phase"] for c in session.calls] == ["probe", "import"]
    assert all(c["offer_id"] == "offered" for c in session.calls)
    assert [c["cost_scope"] for c in session.calls] == ["online", "fixed"]
    assert all("phase" not in data and "cost_scope" not in data for data in sent)
    assert study.observation_context.get()["phase"] == "setup"
    assert study.cap.checker_cases == 2
    session.journal.close()


@pytest.mark.parametrize("case", ["PASS", "FAIL", "invalid", "timeout", "usage_missing"])
async def test_new_wire_original_bytes_and_adverse_observations_share_offline_reader(
    case, tmp_path
):
    from check_gemma_transport import check_native_observation

    from collective_intelligence_overlay.adapters.inference_observer import RawInferenceTransport

    p = World(3, "synthetic-adverse").problem("sql", "L1", "public")
    valid = semantic_rule_baseline(p)
    if case == "FAIL":
        valid["negative_policy"] = "exclude" if valid["negative_policy"] == "include" else "include"
    value = {**valid, "uses": ["invented"]} if case == "invalid" else valid
    native = {
        "model": "gemma4:e4b",
        "done": True,
        "message": {"role": "assistant", "content": json.dumps(value)},
        "prompt_eval_count": 10,
        "eval_count": 20,
    }
    if case == "usage_missing":
        native.pop("eval_count")

    async def respond(request):
        if case == "timeout":
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        return httpx.Response(200, json=native)

    directory = tmp_path / "raw"
    observer = RawInferenceTransport(
        directory,
        identity={"job": "synthetic"},
        requested={"synthetic": True},
        provenance={"model_name": "gemma4:e4b"},
        token_reservation=4352,
        real_model=False,
        delegate=httpx.MockTransport(respond),
    )
    async with httpx.AsyncClient(transport=observer) as client:
        try:
            await client.post(
                "http://127.0.0.1:11444/api/chat",
                json={"model": "gemma4:e4b", "format": wire_schema(p).model_json_schema()},
            )
        except httpx.ReadTimeout:
            pass
    observed = json.loads((directory / "observation.json").read_bytes())
    intent = json.loads((directory / "intent.json").read_bytes())
    final = check_native_observation((directory / "response.raw").read_bytes(), observed, intent)
    assert intent["real_model"] is False
    if case in {"timeout", "usage_missing"}:
        assert observed["tokens_measured"] is None and observed["budget_charge"] == 4352
    elif case == "invalid":
        with pytest.raises(ValidationError):
            compile_slots(p, json.loads(final["message"]["content"]))
    else:
        solution = compile_slots(p, json.loads(final["message"]["content"]))
        assert compare(
            await bounded_execute(solution, p), World(3, "synthetic-adverse").expected(p)
        ) == (case == "PASS")
