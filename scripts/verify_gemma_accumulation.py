"""Offline raw/CAS/DSSE and executable-data verification; never sends inference."""

import argparse
import base64
import hashlib
import json
from pathlib import Path

from accumulation_host import check_metadata_observations, runtime_contract
from accumulation_primitives import Problem, Solution
from accumulation_protocol import schedule, unrelated_world
from accumulation_stock import CognitiveView, Snapshot, ViewSkill, prompt, retrieve
from accumulation_tasks import World, compare
from check_gemma_candidate import check_candidate_observations
from check_gemma_state import (
    check_cognitive_admission,
    check_state_files,
    reconstruct_states,
    retrieval_dose,
)
from check_gemma_transport import (
    check_model_attempt,
    check_native_observation,
    check_originals,
    check_requested_payload,
    check_selected_identity,
    validate_wire,
)
from jsonschema.exceptions import ValidationError as SchemaError
from securesystemslib.signer import Key

from collective_intelligence_overlay.bindings import ArtifactSpec, Binding, fingerprint
from collective_intelligence_overlay.models import (
    Capability,
    Decision,
    Event,
    Evidence,
    FormationInput,
    ReceiptRef,
)
from collective_intelligence_overlay.security import Principal, verify
from collective_intelligence_overlay.storage import projection_digest


def read(path):
    # The cohort aggregates all arms and their resource observations. Keep a
    # separate finite bound; individual raw and signed records retain 32 MiB.
    limit = (128 if path.name == "cohort.json" else 32) * 1024 * 1024
    if path.is_symlink() or path.stat().st_size > limit:
        raise ValueError("unsafe or oversized raw file")
    return json.loads(path.read_bytes())


def reserved_executions(calls, offers):
    # Qualification checks are real calls even though they are not performance
    # offerings. Count their cases from the complete preregistered schedule.
    planned = {offer.id: offer for offer in offers}
    try:
        cases = sum(
            len(planned[call["request"]["offer"]].cases)
            for call in calls
            if call["operation"] == "app.check"
        )
    except KeyError as error:
        raise ValueError("checker call lacks a preregistered offering") from error
    executions = cases + sum(
        call["operation"] in {"invoke", "run", "app.construct", "app.execute"} for call in calls
    )
    return cases, executions


def records(directory, *, new_receiver=False):
    signed, originals, states, artifacts = {}, {}, {}, {}
    owners = ("producer", "receiver", "verifier") + (("newreceiver",) if new_receiver else ())
    for owner in owners:
        exported = read(directory / (owner + "-observations.json"))
        export_summary = read(directory / "export.json")["owners"][owner]
        if len(exported["signed_records"]) != export_summary["signed_record_count"]:
            raise ValueError("missing original signed records")
        principals = {
            name: Principal(
                Key.from_dict(p["keyid"], dict(p["key"])), p["trust_group"], frozenset(p["methods"])
            )
            for name, p in exported["public_identities"].items()
        }
        if exported["owner"] != owner:
            raise ValueError("owner export changed")
        for envelope in exported["signed_records"]:
            record = verify(envelope, principals)
            key = (
                record.kind,
                record.issuer,
                record.subject.key if isinstance(record, Capability) else (record.id),
            )
            original = base64.b64decode(envelope["payload"], validate=True)
            if key in originals and originals[key] != original:
                raise ValueError("conflicting original signed payloads")
            signed[key], originals[key] = record, original
        decision_path = directory / (owner + "-decisions.json")
        if decision_path.exists():
            decisions = read(decision_path)
            if decisions["owner"] != owner or decisions["complete"] is not True:
                raise ValueError("incomplete original safety ledger export")
            if decisions["signed"] is not False:
                raise ValueError("local admission projections are not original signed records")
            seen = set()
            for item in decisions["original_local_projections"]:
                body = Decision.model_validate(item["body"])
                if body.id in seen or projection_digest(item["body"]) != item["projection_digest"]:
                    raise ValueError("local safety projection changed or duplicated")
                seen.add(body.id)
        for row in exported["invocations"]:
            key = owner, row["caller"], row["id"]
            if key in states:
                raise ValueError("duplicate authoritative invocation")
            states[key] = row
        for digest, encoded in read(directory / (owner + "-artifacts.json"))[
            "original_bytes_base64"
        ].items():
            raw = base64.b64decode(encoded, validate=True)
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("CAS original bytes mismatch")
            artifacts[owner, digest] = raw
    return signed, states, artifacts


def execution(value, owner, binding, arguments, signed, states):
    if value.get("state") != "completed":
        return False
    event = signed["event", owner, value["receipt_id"]]
    row = states[owner, value["caller"], value["id"]]
    receipt = event.execution if isinstance(event, Event) else None
    if (
        receipt is None
        or receipt.state != "completed"
        or receipt.invocation_id != value["id"]
        or receipt.caller != value["caller"]
        or receipt.binding_digest != binding.digest
        or receipt.arguments_digest != fingerprint(arguments)
        or receipt.result_digest != fingerprint(value["result"])
        or row["receipt_id"] != event.id
        or row["result"] != value["result"]
        or row["binding_digest"] != binding.digest
        or row["request"]["arguments"] != arguments
        or row["fingerprint"] != fingerprint(row["request"])
    ):
        raise ValueError("signed execution/request/result chain changed")
    return True


def check_construction_lineage(construction, cap, binding, builder, peer, arm, signed, *, copied):
    """Authenticate imported provenance or actual scratch builder lineage."""
    event = construction.get("formation_event")
    formed = arm in {"C", "I", "A"} and not copied
    if (
        cap.subject != binding.subject
        or cap.entrypoint != binding.id
        or cap.classification != ("imported" if copied else "declared-new")
        or cap.license != "Apache-2.0"
    ):
        raise ValueError("candidate is not the original classified executable")
    if not formed:
        if event is not None or cap.formation_inputs or cap.schema_version != "2":
            raise ValueError("copied/ordinary procedure was relabelled observed formation")
        return
    original = signed["event", peer, event["id"]]
    formation = original.formation
    if (
        original.model_dump(mode="json") != event
        or original.subject != binding.subject
        or original.action != "formation"
        or original.outcome != "UNKNOWN"
        or formation is None
        or formation.binding_digest != binding.digest
        or formation.scope != binding.scope
        or formation.relationship != "observed-use"
        or formation.receipts
        != (ReceiptRef(issuer=peer, id=construction["construction"]["receipt_id"]),)
        or cap.schema_version != "3"
        or cap.formation_inputs
        != (FormationInput(subject=builder.subject, issuer=peer, binding_digest=builder.digest),)
    ):
        raise ValueError("scratch formation lacks its original bounded builder lineage")
    receipt = signed["event", peer, formation.receipts[0].id].execution
    if (
        receipt is None
        or receipt.purpose != "reuse"
        or receipt.state != "completed"
        or receipt.binding_digest != builder.digest
        or receipt.scope != builder.scope
        or builder.subject == cap.subject
    ):
        raise ValueError("formation is cyclic or lacks actual completed builder use")


def check_copied_admission(construction, source, peer, arm, directory, signed, artifacts):
    audits = construction["source_admission"]
    if len(audits) != 1:
        raise ValueError("copied executable lacks its actual original source admission")
    body = audits[0]["decision"]
    admitted = body is None or body["outcome"] == "ACCEPT"
    local = read(directory / (peer + "-decisions.json"))
    check_cognitive_admission(
        (source,),
        {
            "admission_records": audits,
            "visible_snapshot": {
                "skills": [ViewSkill.from_skill(source).model_dump(mode="json")] if admitted else []
            },
        },
        peer,
        signed,
        artifacts,
        {r["body"]["id"]: r["body"] for r in local["original_local_projections"]},
        checked=arm in {"C", "I", "A"},
    )
    if not admitted and construction.get("state") == "constructed":
        raise ValueError("copied procedure bypassed original receiver denial")
    return admitted


def inference(path, protocol, offer, attempt, signed, states, artifacts, expected_snapshot=None):
    problem = Problem.model_validate(offer["problem"])
    intent, observed, parsed = (
        read(path / p) for p in ("intent.json", "observation.json", "parsed.json")
    )
    expected = {
        "world": offer["world"],
        "arm": offer["arm"],
        "protocol": protocol["id"],
        "peer": offer["peer"],
        "job": attempt["id"],
        "task": offer["problem"]["id"],
        "view": offer["view"],
        "snapshot_digest": offer["snapshot_digest"],
    }
    if (
        intent["real_model"] is not True
        or intent["provenance"]["model_digest"] != protocol["model_digest"]
        or intent["provenance"]["sources"] != protocol["sources"]
        or any(intent["identity"].get(k) != str(v) for k, v in expected.items())
    ):
        raise ValueError("mock/source/model/arm/world identity mismatch")
    snapshot = (CognitiveView if "full_snapshot_artifact" in parsed else Snapshot).model_validate(
        parsed["visible_snapshot"]
    )
    if "full_snapshot_artifact" in parsed:
        complete_snapshot = Snapshot.model_validate_json(
            artifacts[offer["peer"], parsed["full_snapshot_artifact"]]
        )
        if expected_snapshot is not None and complete_snapshot != expected_snapshot:
            raise ValueError("signed cognitive snapshot is not the ordered training state")
        if complete_snapshot.digest != offer["snapshot_digest"]:
            raise ValueError("original immutable snapshot artifact changed")
    if (
        snapshot.world != offer["world"]
        or snapshot.arm != offer["arm"]
        or snapshot.checkpoint != offer["checkpoint"]
        or parsed["full_snapshot_digest"] != offer["snapshot_digest"]
        or (offer["view"] == "empty" and snapshot.skills)
    ):
        raise ValueError("cognitive view/checkpoint changed")
    raw = (path / "response.raw").read_bytes()
    check_native_observation(raw, observed, intent)
    if observed["final_model"] is not None and observed["final_model"] != protocol["model"]:
        raise ValueError("native response reports a different actual model")
    if hashlib.sha256(raw).hexdigest() != observed["raw_sha256"]:
        raise ValueError("raw inference response changed")
    if intent["settings_digest"] != fingerprint(intent["requested"]):
        raise ValueError("model settings digest changed")
    measured, input_tokens, generated, actual_solution = False, None, None, None
    if observed["transport_dispatch_started"]:
        request = read(path / "request.json")
        actual_request = (path / "request.raw").read_bytes()
        if (
            hashlib.sha256(actual_request).hexdigest() != request["payload_digest"]
            or json.loads(actual_request) != request["payload"]
        ):
            raise ValueError("actual inference request bytes changed")
        payload = request["payload"]
        if intent["provenance"]["schema_digest"] != fingerprint(payload["format"]):
            raise ValueError("actual structured-output schema changed")
        if request["path"] != "/api/chat" or payload["model"] != protocol["model"]:
            raise ValueError("actual backend/model changed")
        options = {**protocol["model_options"], "seed": attempt["model_seed"]}
        if (
            intent["requested"]["native_options"] != options
            or any(payload["options"].get(k) != v for k, v in options.items())
            or payload.get("think") is not False
            or len(payload["messages"]) != 1
            or payload["messages"][0]["role"] != "user"
        ):
            raise ValueError("settings/seed/blank conversation changed")
        text = prompt(problem, snapshot.skills, revision=protocol.get("prompt_revision", "1"))
        if attempt["id"].endswith("-1"):
            text += "\nPrevious attempt public feedback: Previous independent check did not pass"
        if payload["messages"][0]["content"] != text or intent["provenance"][
            "prompt_digest"
        ] != fingerprint(text):
            raise ValueError("prompt/hidden-answer/stock context changed")
        parts = raw.splitlines() if "ndjson" in (observed["content_type"] or "") else [raw]
        frames, errors = [], []
        for i, part in enumerate(parts):
            if not part:
                continue
            try:
                frames.append(json.loads(part))
            except (ValueError, UnicodeError):
                errors.append(i)
        if errors != observed["raw_parse_error_indices"]:
            raise ValueError("partial-stream classification changed")
        final = next((f for f in reversed(frames) if isinstance(f, dict) and f.get("done")), {})
        input_tokens, generated = final.get("prompt_eval_count"), final.get("eval_count")
        measured = bool(
            observed["stream_complete"]
            and observed["status"] == 200
            and not errors
            and type(input_tokens) is int
            and type(generated) is int
            and min(input_tokens, generated) >= 0
        )
        charge = input_tokens + generated if measured else intent["token_reservation"]
        schema = protocol.get("wire_schemas", {}).get(problem.family + "/" + problem.difficulty)
        try:
            if protocol.get("observation_binding_schema") == "2":
                actual_solution = validate_wire(final["message"]["content"], schema, Solution)
            else:
                actual_solution = Solution.model_validate_json(final["message"]["content"])
        except (ValueError, TypeError, KeyError, SchemaError):
            pass
        for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
            native = final.get(key)
            if observed["durations_seconds"][key] != (
                native / 1e9 if type(native) is int else None
            ):
                raise ValueError("backend native-duration conversion changed")
    else:
        charge = 0
        if raw or observed["status"] is not None:
            raise ValueError("inconsistent proven pre-send failure")
    if (
        observed["tokens_measured"] != (input_tokens + generated if measured else None)
        or observed["budget_charge"] != charge
        or parsed["solution"]
        != (actual_solution.model_dump(mode="json") if actual_solution else None)
    ):
        raise ValueError("usage or actual response-to-parsed-procedure changed")
    event = signed["event", offer["peer"], "model-" + attempt["id"]]
    if protocol.get("observation_binding_schema") == "2":
        if event.subject.version != "2":
            raise ValueError("original model event lacks the declared observation binding")
        check_originals(path, observed, parsed, offer["peer"], artifacts)
        check_selected_identity(
            read(path / "model-identity.json"),
            protocol,
            dispatched=observed["transport_dispatch_started"],
        )
        if observed["transport_dispatch_started"]:
            check_requested_payload(
                request, actual_request, intent, protocol, attempt["model_seed"], schema, text
            )
        if expected_snapshot is None:
            raise ValueError("missing ordered cognitive-state reconstruction")
        candidates = retrieve(
            expected_snapshot,
            problem,
            offer["peer"],
            view=offer["view"],
            revision=protocol.get("retrieval_revision", "1"),
        )
        if parsed["retrieval_candidates"] != [
            ViewSkill.from_skill(s).model_dump(mode="json") for s in candidates
        ]:
            raise ValueError("actual retrieval differs from declared eligible stock")
        local = read(path.parents[1] / (offer["peer"] + "-decisions.json"))
        decisions = {r["body"]["id"]: r["body"] for r in local["original_local_projections"]}
        check_cognitive_admission(
            candidates,
            parsed,
            offer["peer"],
            signed,
            artifacts,
            decisions,
            checked=offer["arm"] in {"C", "I", "A"},
        )
    if json.loads(artifacts[offer["peer"], event.subject.digest]) != parsed or event.costs[
        0
    ].quantity != (input_tokens + generated if measured else None):
        raise ValueError("model parsed/CAS/signed cost link changed")
    if "solution" in attempt and attempt["solution"] != parsed["solution"]:
        raise ValueError("actual model procedure was replaced before construction")
    response = attempt["response"]
    row = states.get((offer["peer"], offer["peer"], "propose-" + attempt["id"]))
    if row is None or row["request"]["binding"] != "model-propose":
        raise ValueError("model has no original bounded Executor invocation")
    arguments = row["request"]["arguments"]
    if (
        arguments["model_seed"] != attempt["model_seed"]
        or arguments["problem"] != offer["problem"]
        or arguments["visible_snapshot"] != parsed["visible_snapshot"]
        or arguments["snapshot_digest"] != offer["snapshot_digest"]
    ):
        raise ValueError("model raw response is not the original selected invocation")
    if response.get("state") == "completed":
        if (
            row["state"] != "completed"
            or row["result"] != response["result"]
            or row["receipt_id"] != response["receipt_id"]
        ):
            raise ValueError("proposer result differs from original authoritative receipt")
        receipt = signed["event", offer["peer"], row["receipt_id"]].execution
        if (
            receipt is None
            or receipt.arguments_digest != fingerprint(arguments)
            or receipt.result_digest != fingerprint(row["result"])
        ):
            raise ValueError("proposer result/arguments signature changed")
    return {
        "dispatched": observed["transport_dispatch_started"],
        "complete": observed["stream_complete"],
        "measured": measured,
        "prompt_tokens": input_tokens if measured else None,
        "generated_tokens": generated if measured else None,
        "charge": charge,
        "model_identity_observation_dispatched": read(path / "model-identity.json")[
            "transport_dispatch_started"
        ]
        if protocol.get("observation_binding_schema") == "2"
        else None,
    }


def arm(directory, protocol, world_seed, expected_arm):
    summary = read(directory / "arm-result.json")
    world = World(world_seed)
    if (
        summary["world"] != world.id
        or summary["seed"] != world_seed
        or summary["arm"] != expected_arm
    ):
        raise ValueError("arm/world/seed summary changed")
    signed, states, artifacts = records(
        directory,
        new_receiver=protocol.get("new_receiver", False)
        and summary.get("classification") != "positive-calibration-only",
    )
    if protocol["classification"] == "confirmation":
        check_candidate_observations(
            protocol,
            signed,
            artifacts,
            ("producer", "receiver", "verifier")
            + (
                ("newreceiver",)
                if protocol.get("new_receiver")
                and summary.get("classification") != "positive-calibration-only"
                else ()
            ),
        )
    calls = [json.loads(x) for x in (directory / "calls.jsonl").read_text().splitlines()]
    if sorted(c["call_index"] for c in calls) != list(range(len(calls))):
        raise ValueError("missing/duplicate transport observations")
    observed_models, offered_models = {}, set()
    planned = {}
    if protocol["classification"] == "smoke" and {o["id"] for o in summary["offers"]} != {
        "smoke-0",
        "smoke-1",
    }:
        raise ValueError("missing predeclared connection probe")
    if (
        protocol.get("schedule_schema") in {"1", "2"}
        and summary.get("classification") != "positive-calibration-only"
    ):
        planned = {
            o.id: o for o in schedule(world, expected_arm, protocol) if o.phase != "qualification"
        }
        if {o["id"] for o in summary["offers"]} != set(planned):
            raise ValueError(
                "missing/extra offered tasks; incomplete trajectories are not valid analyses"
            )
    cognitive = reconstruct_states(summary, protocol) if planned else None
    passed = 0
    outcomes = []
    for offer in summary["offers"]:
        if offer["world"] != world.id or offer["arm"] != expected_arm:
            raise ValueError("offered task arm/world changed")
        original = read(directory / "offers" / offer["id"] / "result.json")
        if original != offer:
            raise ValueError("offered result differs from original attempt file")
        if protocol.get("observation_binding_schema") == "2":
            event = signed["event", offer["peer"], "offer-observation-" + offer["id"]]
            raw = (directory / "offers" / offer["id"] / "result.json").read_bytes()
            if (
                event.subject.version != "2"
                or event.task_id != offer["problem"]["id"]
                or event.attempt_id != offer["id"]
                or artifacts[offer["peer"], event.subject.digest] != raw
            ):
                raise ValueError("original offer clock/accounting/state observation changed")
        initial = read(directory / "offers" / offer["id"] / "intent.json")
        for key in (
            "id",
            "peer",
            "world",
            "arm",
            "problem",
            "view",
            "snapshot_digest",
            "checkpoint",
            "episode",
            "learn",
        ):
            if initial[key] != offer[key]:
                raise ValueError("offered intent/selection state changed")
        task_world = world
        if offer.get("task_world", world.id) != world.id:
            task_world = unrelated_world(world)
            if offer["task_world"] != task_world.id:
                raise ValueError("unknown foreign task world")
        if planned:
            expected = planned[offer["id"]]
            if (
                offer["problem"] != expected.problem.model_dump(mode="json")
                or offer["view"] != expected.view
                or offer["phase"] != expected.phase
                or offer["checkpoint"]
                != (expected.episode - 1 if expected.phase == "training" else expected.checkpoint)
                or offer["peer"] != expected.peer
                or offer["task_world"] != expected.world.id
            ):
                raise ValueError("preregistered task/arm/checkpoint/snapshot intervention changed")
        successes = []
        candidates = None
        context_doses = []
        direct_admitted_dose = None
        if (
            protocol.get("observation_binding_schema") == "2"
            and summary.get("classification") != "positive-calibration-only"
        ):
            candidates = retrieve(
                cognitive["offers"][offer["id"]],
                Problem.model_validate(offer["problem"]),
                offer["peer"],
                view=offer["view"],
                revision=protocol["retrieval_revision"],
            )
            if offer.get("retrieval_candidates") != [
                ViewSkill.from_skill(s).model_dump(mode="json") for s in candidates
            ]:
                raise ValueError("offer actual retrieval differs from exact eligible stock")
        for attempt in offer["attempts"]:
            if candidates is not None and attempt["kind"] == "copied-executable":
                if (
                    not candidates
                    or attempt["source_skill"] != candidates[0].model_dump(mode="json")
                    or attempt["solution"] != candidates[0].solution.model_dump(mode="json")
                ):
                    raise ValueError("direct reuse replaced the first eligible original source")
                admitted = check_copied_admission(
                    attempt["construction"],
                    candidates[0],
                    offer["peer"],
                    expected_arm,
                    directory,
                    signed,
                    artifacts,
                )
                direct_admitted_dose = retrieval_dose(
                    [ViewSkill.from_skill(candidates[0]).model_dump(mode="json")]
                    if admitted
                    else []
                )
            if attempt["kind"] == "model" and attempt.get("status") != "not_dispatched_budget":
                if planned:
                    check_model_attempt(
                        offer, attempt, protocol, world_seed, planned[offer["id"]].attempts
                    )
                if attempt["id"] in offered_models:
                    raise ValueError("duplicate original model attempt in offered denominator")
                offered_models.add(attempt["id"])
                observed_models[attempt["id"]] = inference(
                    directory / "model" / attempt["id"],
                    protocol,
                    offer,
                    attempt,
                    signed,
                    states,
                    artifacts,
                    cognitive["offers"][offer["id"]] if cognitive else None,
                )
                if candidates is not None:
                    parsed = read(directory / "model" / attempt["id"] / "parsed.json")
                    context_doses.append(retrieval_dose(parsed["visible_snapshot"]["skills"]))
            succeeded = False
            if attempt.get("construction", {}).get("state") == "constructed":
                construction, checked = attempt["construction"], attempt["check"]
                binding = Binding.model_validate(construction["binding"])
                spec = ArtifactSpec.model_validate_json(
                    artifacts[offer["peer"], binding.artifact_digest]
                )
                if spec.parameters != attempt["solution"]:
                    raise ValueError("selected candidate differs from actual executable parameters")
                cap = signed["capability", offer["peer"], binding.subject.key]
                if cap.binding_digest != binding.digest or cap.scope != binding.scope:
                    raise ValueError("candidate scope differs from signed original")
                builder = Binding.model_validate(
                    next(
                        c["result"]["binding"]
                        for c in calls
                        if c["operation"] == "app.describe" and c["owner"] == offer["peer"]
                    )
                )
                execution(
                    construction["construction"],
                    offer["peer"],
                    # Builder original is authenticated and pinned in the invocation.
                    builder,
                    {"solution": attempt["solution"]},
                    signed,
                    states,
                )
                if candidates is not None:
                    check_construction_lineage(
                        construction,
                        cap,
                        binding,
                        builder,
                        offer["peer"],
                        expected_arm,
                        signed,
                        copied=attempt["kind"] == "copied-executable",
                    )
                transcript = json.loads(artifacts["verifier", checked["artifact_digest"]])
                if (
                    transcript["binding"] != binding.model_dump(mode="json")
                    or transcript["peer"] != offer["peer"]
                    or transcript["offer"] != offer["id"]
                    or transcript["checker_digest"]
                    != protocol["sources"]["scripts/accumulation_tasks.py"]
                    or not 1 <= len(transcript["transcripts"]) <= 4
                ):
                    raise ValueError("independent checker used another binding")
                checker_event = signed[
                    "event",
                    "verifier",
                    "check-event-" + fingerprint([offer["id"], binding.digest])[:32],
                ]
                if (
                    checker_event.subject.digest != checked["artifact_digest"]
                    or checker_event.action != "verification"
                    or checker_event.outcome != checked["verdict"]
                ):
                    raise ValueError("checker output is not the original signed observation")
                if planned and [c["case"]["problem"] for c in transcript["transcripts"]] != [
                    p.model_dump(mode="json") for p in planned[offer["id"]].cases
                ]:
                    raise ValueError("missing/changed independent parallel checker forms")
                actual_pass = True
                for case in transcript["transcripts"]:
                    p = Problem.model_validate(case["case"]["problem"])
                    reference = task_world.expected(p)
                    if reference != case["case"]["expected"]:
                        raise ValueError("independent hidden comparator changed")
                    complete = execution(
                        case["observed"],
                        offer["peer"],
                        binding,
                        {"problem": p.model_dump(mode="json")},
                        signed,
                        states,
                    )
                    truth = complete and compare(case["observed"].get("result"), reference)
                    if case["passed"] != truth:
                        raise ValueError("checker flag differs from original execution")
                    actual_pass &= truth
                if (checked["verdict"] == "PASS") != actual_pass:
                    raise ValueError("independent checker verdict changed")
                if checked["evidence"]:
                    evidence = signed["evidence", "verifier", checked["evidence"]["id"]]
                    if (
                        not isinstance(evidence, Evidence)
                        or evidence.model_dump(mode="json") != checked["evidence"]
                        or evidence.artifact_digest != checked["artifact_digest"]
                    ):
                        raise ValueError("independent signed evidence changed")
                if actual_pass:
                    succeeded = execution(
                        attempt["execution"],
                        offer["peer"],
                        binding,
                        {"problem": offer["problem"]},
                        signed,
                        states,
                    )
            if attempt["succeeded"] != succeeded:
                raise ValueError("attempt success disagrees with original signed execution/checks")
            successes.append(succeeded)
        if offer["succeeded"] != any(successes):
            raise ValueError("offered task denominator/outcome changed")
        passed += offer["succeeded"]
        outcomes.append(
            {
                "id": offer["id"],
                "phase": offer.get("phase", "smoke"),
                "checkpoint": offer["checkpoint"],
                "view": offer["view"],
                "family": offer["problem"]["family"],
                "difficulty": offer["problem"]["difficulty"],
                "condition": offer["problem"]["condition"],
                "succeeded": offer["succeeded"],
                "inclusive_wall_seconds": offer.get("inclusive_wall_seconds"),
                "problem_id": offer["problem"]["id"],
                "retrieved_dose": retrieval_dose(offer["retrieval_candidates"])
                if candidates is not None
                else None,
                "direct_admitted_dose": direct_admitted_dose,
                "model_context_doses": context_doses if candidates is not None else None,
            }
        )
    actual_directories = (
        {p.name for p in (directory / "model").iterdir()}
        if (directory / "model").exists()
        else set()
    )
    if actual_directories != offered_models:
        raise ValueError("missing/extra model attempts, including failed requests")
    if planned:
        check_state_files(directory, cognitive, read)
        resources = read(directory / "resources.json")
        if resources["application_actions"] != len(calls):
            raise ValueError("startup/control transport overhead is missing from aggregate budget")
        if resources["charged_tokens"] != sum(o["charge"] for o in observed_models.values()):
            raise ValueError("whole-world model usage differs from original actual responses")
        if protocol.get("observation_binding_schema") == "2":
            checker_cases, execution_reservations = reserved_executions(
                calls, schedule(world, expected_arm, protocol)
            )
            if (
                resources["model_calls"] != len(observed_models)
                or resources["model_identity_observations_reserved"] != len(observed_models)
                or resources["model_retrieval_calls_reserved"] != len(observed_models)
                or resources["measured_tokens"]
                != sum(o["charge"] for o in observed_models.values() if o["measured"])
                or resources["missing_usage_requests"]
                != sum(o["dispatched"] and not o["measured"] for o in observed_models.values())
                or resources["proven_not_sent_requests"]
                != sum(not o["dispatched"] for o in observed_models.values())
                or resources["checker_cases_reserved"] != checker_cases
                or resources["execution_invocations_reserved"] != execution_reservations
                or resources["retrieval_calls"] != len(summary["offers"])
            ):
                raise ValueError("aggregate reservations or original consumption counters changed")
            for key, field in (
                ("model_identity_observations", "model_identity_observations_reserved"),
                ("execution_invocations", "execution_invocations_reserved"),
                ("checker_cases", "checker_cases_reserved"),
                ("retrieval_calls", "retrieval_calls"),
            ):
                if resources[field] > protocol["caps"][key]:
                    raise ValueError("aggregate observation/execution/checker cap exceeded")
            if (
                resources["retrieval_calls"] + resources["model_retrieval_calls_reserved"]
                > protocol["caps"]["retrieval_calls"]
            ):
                raise ValueError("driver plus child retrieval reservations exceed whole-arm cap")
        if (
            resources["model_calls"] > protocol["caps"]["model_calls"]
            or resources["charged_tokens"] > protocol["caps"]["model_tokens"]
            or resources["application_actions"] > protocol["caps"]["application_actions"]
            or resources["inclusive_wall_seconds"] > protocol["caps"]["wall_seconds"]
        ):
            raise ValueError("aggregate resource cap was exceeded")
        for checkpoint, digest in summary["snapshots"].items():
            snapshot = Snapshot.model_validate(read(directory / f"snapshot-{checkpoint}.json"))
            if snapshot.digest != digest:
                raise ValueError("immutable checkpoint changed")
            trained = {
                o["id"]: o
                for o in summary["offers"]
                if o["learn"] and o["episode"] <= int(checkpoint)
            }
            if any(
                not any(
                    a.get("construction", {}).get("binding", {}).get("id") == skill.id
                    and a["succeeded"]
                    for o in trained.values()
                    for a in o["attempts"]
                )
                for skill in snapshot.skills
            ):
                raise ValueError(
                    "oracle/evaluation/future/foreign procedure entered training stock"
                )
        final = Snapshot.model_validate(read(directory / "final-stock.json"))
        if final.digest != summary["snapshots"]["6"]:
            raise ValueError("readonly evaluation changed final training stock")
        if protocol.get("new_receiver"):
            receiver = Snapshot.model_validate(read(directory / "new-receiver-stock.json"))
            if any(s.producer != "newreceiver" for s in receiver.skills):
                raise ValueError("transfer probe did not use a locally qualified new binding")
            if (
                not summary["new_receiver"]["fresh_database"]
                or not summary["new_receiver"]["fresh_CAS"]
                or summary["new_receiver"]["conversation_transferred"]
                or set(summary["providers_absent"]) != {"producer", "receiver"}
                or any(v["returncode"] is None for v in summary["providers_absent"].values())
            ):
                raise ValueError("blank receiver or physical provider-absence proof missing")
            verify_qualifications(
                summary,
                final,
                receiver,
                world,
                protocol,
                signed,
                states,
                artifacts,
                calls,
                directory=directory,
            )
    return {
        "world": world.id,
        "arm": expected_arm,
        "offered": len(summary["offers"]),
        "passed": passed,
        "model": observed_models,
        "original_signed_records": len(signed),
        "original_CAS_artifacts": len(artifacts),
        "startup_failure": summary.get("error_type"),
        "outcomes": outcomes,
    }


def verify_qualifications(
    summary, final, receiver, world, protocol, signed, states, artifacts, calls, *, directory=None
):
    offered = {
        o.id: o for o in schedule(world, summary["arm"], protocol) if o.phase == "qualification"
    }
    successful = set()
    for q in summary["qualification"]:
        source = next(s for s in final.skills if s.id == q["source_skill"])
        planned = offered[q["id"]]
        if q["problem"] != planned.problem.model_dump(mode="json"):
            raise ValueError("transfer qualification was replaced with its later probe")
        if q["construction"].get("state") != "constructed":
            if q["succeeded"]:
                raise ValueError("unconstructed transfer marked successful")
            continue
        binding = Binding.model_validate(q["construction"]["binding"])
        builder = Binding.model_validate(
            next(
                c["result"]["binding"]
                for c in calls
                if c["operation"] == "app.describe" and c["owner"] == "newreceiver"
            )
        )
        if protocol.get("observation_binding_schema") == "2":
            check_copied_admission(
                q["construction"],
                source,
                "newreceiver",
                summary["arm"],
                directory,
                signed,
                artifacts,
            )
            check_construction_lineage(
                q["construction"],
                signed["capability", "newreceiver", binding.subject.key],
                binding,
                builder,
                "newreceiver",
                summary["arm"],
                signed,
                copied=True,
            )
        if ArtifactSpec.model_validate_json(
            artifacts["newreceiver", binding.artifact_digest]
        ).parameters != source.solution.model_dump(mode="json"):
            raise ValueError("import changed the original executable procedure")
        execution(
            q["construction"]["construction"],
            "newreceiver",
            builder,
            {"solution": source.solution.model_dump(mode="json")},
            signed,
            states,
        )
        checked = q["check"]
        transcript = json.loads(artifacts["verifier", checked["artifact_digest"]])
        event = signed[
            "event", "verifier", "check-event-" + fingerprint([q["id"], binding.digest])[:32]
        ]
        if (
            event.subject.digest != checked["artifact_digest"]
            or transcript["binding"] != binding.model_dump(mode="json")
            or [c["case"]["problem"] for c in transcript["transcripts"]]
            != [p.model_dump(mode="json") for p in planned.cases]
        ):
            raise ValueError("new local capability lacks the original independent recheck")
        all_passed = True
        for case in transcript["transcripts"]:
            p = Problem.model_validate(case["case"]["problem"])
            expected = world.expected(p)
            complete = execution(
                case["observed"],
                "newreceiver",
                binding,
                {"problem": p.model_dump(mode="json")},
                signed,
                states,
            )
            truth = complete and compare(case["observed"].get("result"), expected)
            if case["case"]["expected"] != expected or case["passed"] != truth:
                raise ValueError("new receiver requalification quality changed")
            all_passed &= truth
        success = all_passed and execution(
            q.get("execution", {}),
            "newreceiver",
            binding,
            {"problem": q["problem"]},
            signed,
            states,
        )
        if q["succeeded"] != success:
            raise ValueError("new receiver lacks actual local requalified execution")
        if success:
            successful.add(binding.id)
    if {s.id for s in receiver.skills} != successful:
        raise ValueError("new receiver stock contains unqualified imported or oracle procedures")


def verify_run(directory):
    if (directory / "operator-invalidation-v1.json").exists():
        raise ValueError("operator-declared invalid calibration is excluded from performance")
    protocol = read(directory / "protocol.json")
    if read(directory / "source-manifest.json") != protocol["sources"]:
        raise ValueError("frozen source manifest changed")
    for name, digest in protocol["sources"].items():
        if hashlib.sha256((directory / "source" / name).read_bytes()).hexdigest() != digest:
            raise ValueError("frozen source hash changed")
    manifest = read(directory / "model-manifest.json")
    if (
        manifest["digest"] != protocol["model_digest"]
        or manifest["requested_model"] != protocol["model"]
    ):
        raise ValueError("model/server manifest mismatch")
    metadata_accounting = None
    if protocol["classification"] == "confirmation":
        if runtime_contract(manifest) != protocol["runtime_contract"]:
            raise ValueError("original confirmation runtime differs from preregistered contract")
        metadata_accounting = check_metadata_observations(
            [
                json.loads(line)
                for line in (directory / "model-metadata-calls.jsonl").read_text().splitlines()
            ],
            manifest,
            protocol["owned_server_metadata_calls"],
        )
        samples = (directory / "os-processes.jsonl").read_text().splitlines()
        if not samples or len(samples) > protocol["maximum_OS_observation_samples"]:
            raise ValueError("missing or excessive original OS resource observations")
        registration = read(directory / "cohort.json")["preregistration"]
        if (
            registration["protocol_sha256"]
            != hashlib.sha256((directory / "protocol.json").read_bytes()).hexdigest()
            or registration["installed_wheel_sha256"] != protocol["installed_wheel"]["sha256"]
        ):
            raise ValueError("original preregistration/candidate binding changed")
        cleanup = read(directory / "cleanup.json")
        if (
            cleanup["errors"]
            or not cleanup["owned_server_physically_stopped"]
            or not cleanup["process_observer_physically_stopped"]
            or cleanup["cleanup_grace_seconds"] != protocol["cleanup_grace_seconds"]
            or not 0 <= cleanup["cleanup_wall_seconds"] <= protocol["cleanup_grace_seconds"]
            or cleanup["inclusive_cohort_wall_including_cleanup_seconds"]
            > protocol["cohort_wall_seconds"] + protocol["cleanup_grace_seconds"]
        ):
            raise ValueError("owned physical cleanup or complete cohort wall cap failed")
    results = [
        arm(directory / (World(seed).id + "-" + a), protocol, seed, a)
        for seed in protocol["world_seeds"]
        for a in protocol["arms"]
    ]
    cohort = read(directory / "cohort.json")
    declared = {(World(seed).id, a) for seed in protocol["world_seeds"] for a in protocol["arms"]}
    if (
        len(cohort["arms"]) != len(declared)
        or {(a["world"], a["arm"]) for a in cohort["arms"]} != declared
    ):
        raise ValueError("missing/duplicate independent world arm")
    for a in cohort["arms"]:
        if a != read(directory / (a["world"] + "-" + a["arm"]) / "arm-result.json"):
            raise ValueError("cohort differs from the original independent arm result")
    controls = [
        arm(directory / (World(seed).id + "-positive"), protocol, seed, "E")
        for seed in protocol.get("positive_control_seeds", ())
    ]
    return {
        "verified": True,
        "classification": protocol["classification"],
        "arms": results,
        "positive_controls": controls,
        "owned_server_metadata_accounting": metadata_accounting,
        "network_or_inference_sent_by_verifier": False,
        "interpretation": "raw consistency under trusted local host; no model attestation",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from collective_intelligence_overlay.adapters.inference_observer import write_new

    try:
        result = verify_run(args.run)
    except Exception as error:
        write_new(
            args.output,
            {"verified": False, "error_type": type(error).__name__, "reason": str(error)},
        )
        raise
    write_new(args.output, result)


if __name__ == "__main__":
    main()
