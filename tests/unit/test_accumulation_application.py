"""Deterministic scientific/safety checks, with no model response fixtures."""

import json
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from accumulation_primitives import (  # noqa: E402
    ENVIRONMENT,
    Solution,
    Table,
    execute_solution,
    factory,
    readonly_sql,
)
from accumulation_stock import Skill, Snapshot, prompt, retrieve  # noqa: E402
from accumulation_tasks import LEVELS, World, compare  # noqa: E402
from check_gemma_state import (  # noqa: E402
    check_cognitive_admission,
    matched_retrieval_dose,
    retrieval_dose,
)

from collective_intelligence_overlay.bindings import ArtifactSpec, Binding, Target, callable_digest
from collective_intelligence_overlay.models import (
    Capability,
    Decision,
    Evidence,
    Scope,
    Subject,
    UseRequest,
    now,
)
from collective_intelligence_overlay.security import digest
from collective_intelligence_overlay.storage import projection_digest


@pytest.mark.parametrize("seed", [91831, 51912, 74093])
@pytest.mark.parametrize("difficulty", LEVELS)
@pytest.mark.parametrize("revision", ["1", "2"])
async def test_independent_business_oracle_and_numerical_controls(seed, difficulty, revision):
    world = World(seed)
    for reduction in ("sum", "mean", "count"):
        p = world.sales(
            "unit-control-" + reduction, difficulty, revision=revision, reduction=reduction
        )
        observed = await execute_solution(world.oracle(p), p)
        assert compare(observed, world.expected(p))
        canonical = type(p).model_validate_json(
            json.dumps(p.model_dump(mode="json"), sort_keys=True)
        )
        assert world.expected(canonical) == world.expected(p)
        assert compare(await execute_solution(world.oracle(p), canonical), world.expected(p))
        assert len(world.expected(p)["rows"]) >= 2
        changed = Solution(family="sql", sql="SELECT 'impossible-region' AS 'group',7 AS value")
        assert not compare(await execute_solution(changed, p), world.expected(p))
        wrong = {"rows": [{"group": "impossible-region", "value": 7}]}
        assert not compare(wrong, world.expected(p))
    p = world.calibration("unit-control-calibration", difficulty, revision=revision)
    assert compare(await execute_solution(world.oracle(p), p), world.expected(p))
    assert not compare({"values": [0] * len(p.values)}, world.expected(p))


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM orders",
        "DROP TABLE orders",
        "PRAGMA table_info(orders)",
        "ATTACH DATABASE ':memory:' AS stolen",
        "SELECT * FROM sqlite_master",
        "SELECT load_extension('x')",
        "SELECT randomblob(1000000000)",
        "SELECT 1; SELECT 2",
    ],
)
def test_compiled_sql_authorizer_denies_untrusted_effects_catalog_and_functions(query):
    problem = World(91831).sales("unit-safety", "low")
    original = problem.model_dump_json()
    with pytest.raises((sqlite3.Error, ValueError)):
        readonly_sql(query, problem)
    assert problem.model_dump_json() == original


def test_sql_step_row_and_value_limits_are_actual_parser_and_execution_limits():
    problem = World(91831).sales("unit-limits", "low")
    with pytest.raises(sqlite3.OperationalError, match="interrupted"):
        readonly_sql(
            'SELECT "huge" AS "group",count(*) AS value FROM orders a,orders b,orders c',
            problem,
            maximum_steps=100,
        )
    with pytest.raises(ValueError, match="row bound"):
        readonly_sql('SELECT "many" AS "group",1 AS value FROM orders a,orders b', problem)
    with pytest.raises(ValueError, match="numeric"):
        readonly_sql('SELECT "bad" AS "group",NULL AS value', problem)


def skill(world, peer="producer", *, evidence="checked", invalidated=False):
    problem = world.calibration("unit-memory", "middle")
    solution = world.oracle(problem)
    spec = ArtifactSpec(
        builder_id="study-plan",
        builder_version="1",
        builder_source=callable_digest(factory),
        parameters=solution.model_dump(mode="json"),
        environment=ENVIRONMENT,
    )
    artifact = digest(spec.model_dump_json().encode())
    binding = Binding(
        binding_schema="2",
        artifact_digest=artifact,
        id="skill-" + peer,
        revision=artifact[:24],
        issuer=peer,
        registrar=peer,
        subject=Subject(id="study-test", version=artifact[:24], digest=artifact),
        target=Target(
            kind="local",
            name="study-test",
            interface_digest=callable_digest(factory(solution.model_dump(mode="json"))),
            implementation_identity="installed",
        ),
        scope=Scope(
            task=problem.contract,
            input_contract="problem.v1",
            output_contract="output.v1",
            environment=ENVIRONMENT,
        ),
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        callers=(peer,),
        effects="read-only",
    )
    return Skill(
        id="skill-" + peer,
        producer=peer,
        family="calibration",
        contract=problem.contract,
        revision=problem.revision,
        schema_digest=problem.schema_digest,
        solution=solution,
        basic_passed=True,
        independent_verdict="PASS",
        evidence_id=evidence,
        binding_digest=binding.digest,
        artifact_digest=artifact,
        source_binding=binding,
        source_problem=problem,
        source_world=world.id,
        episode=1,
        invalidated=invalidated,
    )


def test_full_empty_private_shared_and_ordinary_shared_skills_are_distinct_readonly_views():
    world = World(91831)
    problem = world.calibration("unit-probe", "middle")
    skills = (skill(world), skill(world, "receiver"))
    stock = Snapshot(world=world.id, arm="C", checkpoint=4, skills=skills)
    original = stock.model_dump_json(), stock.digest
    assert len(retrieve(stock, problem, "receiver", view="full")) == 2
    assert retrieve(stock, problem, "receiver", view="empty") == ()
    assert len(retrieve(stock.model_copy(update={"arm": "I"}), problem, "receiver")) == 1
    ordinary = stock.model_copy(update={"arm": "M", "skills": (skill(world, evidence=None),)})
    assert len(retrieve(ordinary, problem, "receiver")) == 1
    assert retrieve(ordinary.model_copy(update={"arm": "C"}), problem, "receiver") == ()
    assert retrieve(stock, world.calibration("drift", "middle", revision="2"), "receiver") == ()
    withdrawn = stock.model_copy(update={"skills": (skill(world, invalidated=True),)})
    assert retrieve(withdrawn, problem, "receiver") == ()
    assert (stock.model_dump_json(), stock.digest) == original


def test_blank_prompt_contains_only_current_public_problem_and_explicit_view():
    world = World(91831)
    problem = world.sales("unit-context", "high")
    value = json.loads(prompt(problem, ()).split("\n", 1)[1])
    assert set(value) == {"current_problem", "skills"} and value["skills"] == []
    assert set(value["current_problem"]) == set(problem.model_dump())
    assert all(
        len(t["public_example_rows"]) <= 3 for t in value["current_problem"]["tables"].values()
    )
    assert not {"seed", "expected", "truth", "oracle", "history"} & set(value["current_problem"])
    other = world.sales("unused-parallel-form", "high")
    assert problem.id != other.id and problem.tables != other.tables
    assert problem.contract == other.contract and problem.schema_digest == other.schema_digest


def test_snapshot_cannot_include_future_or_duplicate_artifacts_and_nonfinite_data():
    world = World(91831)
    s = skill(world)
    with pytest.raises(ValidationError, match="future"):
        Snapshot(world=world.id, arm="M", checkpoint=0, skills=(s,))
    with pytest.raises(ValidationError, match="duplicate"):
        Snapshot(world=world.id, arm="M", checkpoint=4, skills=(s, s))
    with pytest.raises(ValidationError, match="finite"):
        Table(columns={"x": "REAL"}, column_order=("x",), rows=[[float("nan")]])


def test_stock_requires_exact_executable_bytes_and_independent_placebo_origin():
    world, unrelated = World(91831), World(71492)
    s = skill(world)
    manifest = ArtifactSpec(
        builder_id="study-plan",
        builder_version="1",
        builder_source=callable_digest(factory),
        parameters=s.solution.model_dump(mode="json"),
        environment=ENVIRONMENT,
    )
    raw = manifest.model_dump_json().encode()
    assert s.validate_artifact(raw).parameters == s.solution.model_dump(mode="json")
    with pytest.raises(ValueError, match="digest"):
        s.validate_artifact(raw + b" ")
    changed = s.model_copy(
        update={"solution": s.solution.model_copy(update={"coefficients": (91, 1, 0)})}
    )
    with pytest.raises(ValueError, match="persisted executable"):
        changed.validate_artifact(raw)
    stock = Snapshot(world=world.id, arm="M", checkpoint=1, skills=(s,))
    with pytest.raises(ValueError, match="relabelled"):
        retrieve(stock, s.source_problem, "receiver", view="irrelevant")
    with pytest.raises(ValidationError, match="another world"):
        Snapshot(world=world.id, arm="M", checkpoint=1, skills=(skill(unrelated),))
    placebo = Snapshot(
        world=world.id,
        arm="M",
        checkpoint=1,
        skills=(skill(unrelated),),
        origin="irrelevant",
        matched_snapshot_digest=stock.digest,
    )
    assert len(retrieve(placebo, s.source_problem, "receiver", view="irrelevant")) == 1
    with pytest.raises(ValidationError, match="independent origin"):
        Snapshot(
            world=world.id,
            arm="M",
            checkpoint=1,
            skills=(s,),
            origin="irrelevant",
            matched_snapshot_digest=stock.digest,
        )


def test_shared_model_cap_is_conservative_and_does_not_multiply_by_peer():
    from accumulation_session import SharedCap

    cap = SharedCap(
        {"model_calls": 2, "model_tokens": 20, "wall_seconds": 60, "application_actions": 3},
        context=8,
        predict=2,
    )
    assert cap.reserve_model()
    cap.settle_model({"tokens_measured": 6})
    assert cap.reserve_model()
    cap.settle_model(None)
    assert not cap.reserve_model()
    assert cap.report()["charged_tokens"] == 16
    assert cap.report()["measured_tokens"] == 6
    assert cap.report()["missing_usage_requests"] == 1
    assert cap.report()["model_identity_observations_reserved"] == 2
    assert cap.report()["model_retrieval_calls_reserved"] == 2
    cap.action()
    cap.action()
    cap.action()
    with pytest.raises(ValueError, match="aggregate"):
        cap.action()


async def test_pre_model_failure_preserves_offering_and_advances_failed_training_checkpoint(
    tmp_path,
):
    from accumulation_session import SharedCap, StudySession

    world = World(91831)
    study = StudySession.__new__(StudySession)
    study.world, study.arm, study.protocol = world, "M", {"id": "unit-only-failure"}
    study.output = tmp_path
    study.cap = SharedCap(
        {
            "model_calls": 2,
            "model_tokens": 20,
            "wall_seconds": 60,
            "application_actions": 3,
            "retrieval_calls": 0,
        },
        context=8,
        predict=2,
    )
    study.stock = Snapshot(world=world.id, arm="M", checkpoint=0, skills=())
    p = world.sales("unit-failed-training", "low")
    result = await study.offer(
        "producer", "failed-training", p, study.stock, episode=1, learn=True, phase="training"
    )
    assert result["error_type"] == "ValueError"
    assert not result["succeeded"] and not result["learning_succeeded"]
    assert study.stock.checkpoint == 1 and not study.stock.skills
    assert result["budget_after"]["model_calls"] == 0
    assert json.loads((tmp_path / "offers/failed-training/result.json").read_bytes()) == result


def test_irrelevant_retrieval_uses_same_contract_filter_and_measures_actual_dose():
    from accumulation_protocol import unrelated_world
    from accumulation_stock import ViewSkill

    world = World(91831)
    original = skill(world)
    foreign = skill(unrelated_world(world))
    stock = Snapshot(world=world.id, arm="M", checkpoint=1, skills=(original,))
    pool = Snapshot(
        world=world.id,
        arm="M",
        checkpoint=1,
        skills=(foreign,),
        origin="irrelevant",
        matched_snapshot_digest=stock.digest,
    )
    p = original.source_problem
    left = retrieve(stock, p, "receiver", revision="2")
    right = retrieve(pool, p, "receiver", view="irrelevant", revision="2")
    assert left == (original,) and right == (foreign,)
    doses = [
        retrieval_dose([ViewSkill.from_skill(s).model_dump(mode="json") for s in v])
        for v in (left, right)
    ]
    assert matched_retrieval_dose(*doses)
    changed = p.model_copy(update={"contract": "another-business-contract"})
    assert retrieve(pool, changed, "receiver", view="irrelevant", revision="2") == ()
    assert retrieve(pool, changed, "receiver", view="irrelevant", revision="1") == (foreign,)
    assert not matched_retrieval_dose(doses[0], retrieval_dose([]))
    mismatch = {**doses[1], "family_contract_revision_counts": {"sql/other/1": 1}}
    assert not matched_retrieval_dose(doses[0], mismatch)
    assert not matched_retrieval_dose(
        doses[0],
        {**doses[1], "serialized_cognitive_bytes": doses[0]["serialized_cognitive_bytes"] * 3},
    )


@pytest.mark.parametrize("checked", [False, True])
@pytest.mark.parametrize(
    "target",
    ["original", "decision_outcome", "changed_scope", "missing_artifact", "missing_evidence"],
)
def test_exact_cognitive_source_and_local_admission_readership(checked, target):
    from accumulation_stock import ViewSkill

    item = skill(World(91831))
    binding = item.source_binding
    raw = (
        ArtifactSpec(
            builder_id="study-plan",
            builder_version="1",
            builder_source=callable_digest(factory),
            parameters=item.solution.model_dump(mode="json"),
            environment=ENVIRONMENT,
        )
        .model_dump_json()
        .encode()
    )
    cap = Capability(
        schema_version="2",
        issuer=item.producer,
        subject=binding.subject,
        binding_digest=binding.digest,
        scope=binding.scope,
        entrypoint=binding.id,
        claim="synthetic-task-contract",
        license="Apache-2.0",
        provenance="deterministic unit only",
        classification="declared-new",
        expires_at=now() + timedelta(hours=1),
    )
    evidence = Evidence(
        schema_version="2",
        id=item.evidence_id,
        issuer="verifier",
        subject=cap.subject,
        binding_digest=cap.binding_digest,
        claim=cap.claim,
        scope=cap.scope,
        receivers=("receiver",),
        verdict="PASS",
        method="reference-check",
        verifier_version="unit",
        artifact_digest="a" * 64,
        expires_at=now() + timedelta(hours=1),
    )
    decision = Decision(
        request=UseRequest(
            receiver="receiver",
            capability_issuer=cap.issuer,
            subject=cap.subject,
            binding_digest=cap.binding_digest,
            scope=cap.scope,
            semantic_fit="confirmed",
        ),
        outcome="ACCEPT",
        reasons=("unit local projection",),
        policy_digest="b" * 64,
    )
    body = decision.model_dump(mode="json") if checked else None
    parsed = {
        "admission_records": [
            {
                "skill_id": item.id,
                "capability_subject_key": cap.subject.key,
                "decision": body,
                "decision_projection_digest": projection_digest(body) if body else None,
            }
        ],
        "visible_snapshot": {"skills": [ViewSkill.from_skill(item).model_dump(mode="json")]},
    }
    signed = {
        ("capability", item.producer, cap.subject.key): cap,
        ("evidence", "verifier", item.evidence_id): evidence,
    }
    artifacts = {("receiver", item.artifact_digest): raw}
    decisions = {decision.id: body} if checked else {}
    if target == "decision_outcome":
        parsed["visible_snapshot"]["skills"] = []
    elif target == "changed_scope":
        signed["capability", item.producer, cap.subject.key] = cap.model_copy(
            update={"license": "unknown"}
        )
    elif target == "missing_artifact":
        artifacts.clear()
    elif target == "missing_evidence":
        signed.pop(("evidence", "verifier", item.evidence_id))
    valid = target == "original" or (not checked and target == "missing_evidence")
    if valid:
        check_cognitive_admission(
            (item,), parsed, "receiver", signed, artifacts, decisions, checked=checked
        )
    else:
        with pytest.raises((ValueError, KeyError)):
            check_cognitive_admission(
                (item,), parsed, "receiver", signed, artifacts, decisions, checked=checked
            )


def test_model_wire_schema_cannot_complete_by_omitting_the_executable_parameters():
    from accumulation_application import ModelDraft

    schema = ModelDraft.model_json_schema()
    assert set(schema["required"]) == set(schema["properties"])
    with pytest.raises(ValidationError):
        ModelDraft.model_validate({"family": "calibration"})
    assert ModelDraft.model_validate(
        {
            "family": "calibration",
            "sql": "",
            "coefficients": [0, 2, 0],
            "reduction": "sum",
            "calibration_order": "not-applicable",
            "uses": [],
            "explanation": "linear",
        }
    )


@pytest.mark.parametrize("seed", [91831, 51912, 74093])
async def test_new_cross_family_workflow_is_not_rename_and_changes_actual_output(seed):
    world = World(seed)
    problem = world.composition("unit-unseen-connector")
    solution = world.oracle(problem)
    assert compare(await execute_solution(solution, problem), world.expected(problem))
    # Same metadata/name with a wrong numerical callable changes held-out quality.
    changed = solution.model_copy(update={"coefficients": (100, 1, 0)})
    assert not compare(await execute_solution(changed, problem), world.expected(problem))
    wrong_order = solution.model_copy(update={"calibration_order": "reduce-then-calibrate"})
    assert not compare(await execute_solution(wrong_order, problem), world.expected(problem))
    with pytest.raises(ValueError, match="wrong callable"):
        await execute_solution(Solution(family="calibration"), problem)
    # A learned sales query cannot execute the new connector: items/conversions
    # are absent and the output must precede individual nonlinear calibration.
    old = world.oracle(world.sales("unit-old-business", "middle"))
    with pytest.raises(sqlite3.Error):
        readonly_sql(old.sql, problem)


@pytest.mark.parametrize(
    "malformed",
    [
        {"rows": [{"group": [], "value": 1}]},
        {"rows": []},
        {"values": [float("nan")]},
        {"values": [True]},
        {"extra": []},
    ],
)
def test_comparator_preserves_false_negative_missing_and_malformed_outputs(malformed):
    expected = {"values": [1]} if "values" in malformed else {"rows": [{"group": "g", "value": 1}]}
    assert compare(malformed, expected) is False
