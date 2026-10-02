"""Exercise recovery event guards and the real shallow-checkout failure."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def resume_module():
    path = Path(__file__).parents[2] / ".github/scripts/publication_resume.py"
    spec = importlib.util.spec_from_file_location("tested_publication_resume", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def trusted_environment(module):
    return {
        "GITHUB_REPOSITORY": module.REPOSITORY,
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": module.REPOSITORY + "/" + module.WORKFLOW + "@refs/heads/main",
        "CIO_PUBLICATION_RESUME": "true",
        "CIO_VALIDATION_SCOPE": "full",
        "CIO_PRODUCTION_PROTOCOLS": "false",
        "CIO_VERIFY_PYPI": "false",
        "GITHUB_RUN_ID": "123",
    }


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("GITHUB_REPOSITORY", "other/fork"),
        ("GITHUB_EVENT_NAME", "push"),
        ("GITHUB_REF", "refs/tags/v0.4.1"),
        ("GITHUB_WORKFLOW_REF", "other/workflow.yml@refs/heads/main"),
        ("CIO_PUBLICATION_RESUME", "false"),
        ("CIO_VALIDATION_SCOPE", "representative"),
        ("CIO_PRODUCTION_PROTOCOLS", "true"),
        ("CIO_VERIFY_PYPI", "true"),
        ("GITHUB_RUN_ID", "untrusted"),
    ],
)
def test_only_explicit_trusted_full_main_recovery_is_allowed(resume_module, key, value):
    environment = trusted_environment(resume_module)
    resume_module.require_event(environment)
    environment[key] = value
    with pytest.raises(AssertionError):
        resume_module.require_event(environment)


@pytest.fixture
def recovery_repository(resume_module, tmp_path):
    module = resume_module
    root = tmp_path / "engine"
    root.mkdir()

    def command(*arguments, cwd=root, check=True):
        return subprocess.run(
            ["git", *arguments], cwd=cwd, check=check, capture_output=True, text=True
        )

    def write(name, content):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit():
        command("add", ".")
        command(
            "-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-m", "fixture"
        )
        return module.git(root, "rev-parse", "HEAD")

    command("init")
    write("original.txt", "Original candidate ancestor\n")
    candidate_commit = commit()
    manifest = {
        "candidate_run_id": "456",
        "source_commit": candidate_commit,
        "gate_sha256": "c" * 64,
    }
    write("docs/release-041.json", json.dumps(manifest))
    tag_commit = commit()
    command(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.test",
        "tag",
        "-a",
        "v0.4.1",
        "-m",
        "immutable fixture",
    )
    tag_object = module.git(root, "rev-parse", "refs/tags/v0.4.1")
    declaration = {
        "id": "test-resume",
        "repository": module.REPOSITORY,
        "tag": "v0.4.1",
        "tag_object": tag_object,
        "tag_commit": tag_commit,
        "candidate_run_id": "456",
        "candidate_source_commit": candidate_commit,
        "gate_sha256": "c" * 64,
    }
    write(".github/publication-resume-041.json", json.dumps(declaration))
    write(module.WORKFLOW, "Actual repair workflow\n")
    write(".github/scripts/publication_resume.py", "Actual repair selector\n")
    engine_commit = commit()
    environment = {**trusted_environment(module), "GITHUB_SHA": engine_commit}
    tagged = tmp_path / "tagged"
    command("clone", "--depth=1", "--branch", "v0.4.1", root.as_uri(), str(tagged))
    return module, root, tagged, environment, declaration, command


def test_full_history_recovers_ancestor_without_moving_tag(recovery_repository):
    module, engine, tagged, environment, declaration, command = recovery_repository
    original_object = module.git(tagged, "rev-parse", "refs/tags/v0.4.1")
    missing = command(
        "merge-base",
        "--is-ancestor",
        declaration["candidate_source_commit"],
        "HEAD",
        cwd=tagged,
        check=False,
    )
    assert missing.returncode == 128
    with pytest.raises(AssertionError):
        module.context(engine, tagged, environment)
    command("fetch", "--unshallow", cwd=tagged)
    command(
        "merge-base", "--is-ancestor", declaration["candidate_source_commit"], "HEAD", cwd=tagged
    )
    _, _, provenance = module.context(engine, tagged, environment)
    assert module.git(tagged, "rev-parse", "refs/tags/v0.4.1") == original_object
    assert provenance["immutable_tag_object"] == original_object
    assert provenance["actual_engine_source_commit"] == environment["GITHUB_SHA"]
    assert provenance["tagged_validation_sources_changed"] is False
    assert provenance["new_native_or_model_samples"] == 0
    environment["GITHUB_SHA"] = declaration["tag_commit"]
    with pytest.raises(AssertionError):
        module.context(engine, tagged, environment)


def test_different_tag_or_candidate_cannot_reuse_recovery(recovery_repository):
    module, engine, tagged, environment, declaration, command = recovery_repository
    command("fetch", "--unshallow", cwd=tagged)
    environment["CIO_CANDIDATE_RUN_ID"] = "999"
    with pytest.raises(AssertionError):
        module.context(engine, tagged, environment)
    environment["CIO_CANDIDATE_RUN_ID"] = "456"
    command("checkout", declaration["candidate_source_commit"], cwd=tagged)
    with pytest.raises(AssertionError):
        module.context(engine, tagged, environment)
