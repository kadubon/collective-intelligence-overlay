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


def test_restart_inspection_retains_original_event_and_rejects_changed_bytes(identities):
    from accumulation_application import retain_runtime_inspection

    from collective_intelligence_overlay.models import Event, Subject

    saved = Event(
        id="candidate-installed-runtime",
        issuer="producer",
        subject=Subject(id="study-installed-candidate", version="1", digest="a" * 64),
        action="verification",
        task_id="startup",
        attempt_id="startup",
        correlation_id="startup",
    )
    calls = []
    store = SimpleNamespace(
        record_page=lambda query, limit: SimpleNamespace(items=(saved,)),
        put=lambda envelope: calls.append(envelope),
    )
    app = SimpleNamespace(
        store=store, config=SimpleNamespace(owner="producer"), identity=identities["producer"]
    )
    retain_runtime_inspection(app, "a" * 64)
    assert calls == []
    with pytest.raises(ValueError, match="changed across process restart"):
        retain_runtime_inspection(app, "b" * 64)
    store.record_page = lambda query, limit: SimpleNamespace(items=())
    retain_runtime_inspection(app, "a" * 64)
    assert len(calls) == 1


def test_G3_private_namespace_is_distinct_from_calibration_and_other_arm(tmp_path):
    from run_bounded_scratch import make_plan

    w = World(944110, "screen-L1-sql")
    original_home = tmp_path / (w.id + "-M")
    original_home.mkdir()
    for arm in ("M", "C"):
        home = tmp_path / ("G3-" + arm + "-sql") / (w.id + "-" + arm)
        assert home != original_home and not home.exists()
    plan = make_plan(w, "sql", "L1", "restart-qualify")
    assert plan[3].id != w.problem("sql", "L1", "qualify/public").id
    assert plan[3].contract == w.problem("sql", "L1", "qualify/public").contract


async def test_restart_reuses_binding_with_fresh_execution_id():
    from collective_intelligence_overlay.bindings import Binding, Target
    from collective_intelligence_overlay.models import Scope, Subject

    world = World(944110, "screen-L1-sql")
    problem = world.problem("sql", "L1", "restart-qualify/public")
    binding = Binding(
        binding_schema="2",
        artifact_digest="a" * 64,
        id="persisted-plan",
        revision="a" * 24,
        issuer="receiver",
        registrar="receiver",
        subject=Subject(id="plan", version="1", digest="a" * 64),
        target=Target(
            kind="local",
            name="plan",
            interface_digest="b" * 64,
            implementation_identity="installed",
        ),
        scope=Scope(
            task=problem.contract,
            input_contract="problem.v1",
            output_contract="output.v1",
            environment={"runtime": "unit-test"},
        ),
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        callers=("receiver",),
        effects="read-only",
    )
    requests = []

    async def call(destination, **request):
        requests.append(request)
        if request["operation"] == "app.construct":
            assert request["id"] == "qualify"
            return {"state": "constructed", "binding": binding.model_dump(mode="json")}
        if request["operation"] == "app.check":
            return {"verdict": "PASS"}
        assert request["id"] == "restart-qualify"
        assert request["name"] == binding.id
        return {"state": "completed"}

    async def maintain(*args):
        pass

    study = StudySession.__new__(StudySession)
    study.call, study.maintain_sources = call, maintain
    study.arm, study.protocol = "M", {}
    result = await study.check_constructed(
        "receiver",
        "restart-qualify",
        problem,
        world.oracle(problem),
        "qualify",
        copied=True,
        execution_identifier="restart-qualify",
    )
    assert result["succeeded"]
    assert [r["operation"] for r in requests] == ["app.construct", "app.check", "app.execute"]


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
