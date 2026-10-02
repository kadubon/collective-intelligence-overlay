"""Resume only the declared immutable 0.4.1 tag through trusted main OIDC.

Original package/native gates execute against the unchanged tagged tree. The
actual dispatch workflow/selector has separate source and hash provenance.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

REPOSITORY = "kadubon/collective-intelligence-overlay"
WORKFLOW = ".github/workflows/workflow.yml"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root, *arguments):
    return subprocess.check_output(["git", *arguments], cwd=root, text=True).strip()


def require_event(environment):
    assert environment["GITHUB_REPOSITORY"] == REPOSITORY
    assert environment["GITHUB_EVENT_NAME"] == "workflow_dispatch"
    assert environment["GITHUB_REF"] == "refs/heads/main"
    assert environment["GITHUB_WORKFLOW_REF"] == REPOSITORY + "/" + WORKFLOW + "@refs/heads/main"
    assert environment["CIO_PUBLICATION_RESUME"] == "true"
    assert environment["CIO_VALIDATION_SCOPE"] == "full"
    assert environment["CIO_PRODUCTION_PROTOCOLS"] == "false"
    assert environment["CIO_VERIFY_PYPI"] == "false"
    assert environment["GITHUB_RUN_ID"].isdigit()


def context(engine, tagged, environment):
    require_event(environment)
    declaration_path = engine / ".github/publication-resume-041.json"
    declaration = json.loads(declaration_path.read_bytes())
    assert declaration["repository"] == REPOSITORY and declaration["tag"] == "v0.4.1"
    assert git(engine, "rev-parse", "HEAD") == environment["GITHUB_SHA"]
    assert git(tagged, "rev-parse", "HEAD") == declaration["tag_commit"]
    assert git(tagged, "rev-parse", "refs/tags/v0.4.1") == declaration["tag_object"]
    assert git(tagged, "rev-parse", "refs/tags/v0.4.1^{commit}") == declaration["tag_commit"]
    assert git(tagged, "rev-parse", "--is-shallow-repository") == "false"
    manifest = json.loads((tagged / "docs/release-041.json").read_bytes())
    assert manifest["candidate_run_id"] == declaration["candidate_run_id"]
    assert manifest["source_commit"] == declaration["candidate_source_commit"]
    assert manifest["gate_sha256"] == declaration["gate_sha256"]
    assert environment.get("CIO_CANDIDATE_RUN_ID", "") in {"", declaration["candidate_run_id"]}
    subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            declaration["tag_commit"],
            environment["GITHUB_SHA"],
        ],
        cwd=engine,
        check=True,
    )
    return (
        declaration,
        manifest,
        {
            "id": declaration["id"],
            "repository": REPOSITORY,
            "actual_event": "workflow_dispatch",
            "actual_ref": "refs/heads/main",
            "actual_run_id": environment["GITHUB_RUN_ID"],
            "actual_engine_source_commit": environment["GITHUB_SHA"],
            "actual_engine_source_tree": git(engine, "rev-parse", "HEAD^{tree}"),
            "actual_engine_workflow_sha256": sha(engine / WORKFLOW),
            "actual_selector_sha256": sha(engine / ".github/scripts/publication_resume.py"),
            "actual_declaration_sha256": sha(declaration_path),
            "immutable_tag_object": declaration["tag_object"],
            "immutable_tag_commit": declaration["tag_commit"],
            "original_candidate_run_id": declaration["candidate_run_id"],
            "original_gate_sha256": declaration["gate_sha256"],
            "tagged_validation_sources_changed": False,
            "new_native_or_model_samples": 0,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("select", "verify"))
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--tag-root", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, default=Path(".local/candidate"))
    args = parser.parse_args()
    engine, tagged = args.engine_root.resolve(), args.tag_root.resolve()
    declaration, manifest, provenance = context(engine, tagged, os.environ)
    # Import the actual immutable tag's validator, not modified main gate code.
    sys.path.insert(0, str(tagged / "scripts"))
    from release_gate import api, trusted_run

    tag = api("/git/ref/tags/v0.4.1")
    assert tag["object"]["type"] == "tag"
    assert tag["object"]["sha"] == declaration["tag_object"]
    original_tag = api("/git/tags/" + declaration["tag_object"])
    assert original_tag["object"]["sha"] == declaration["tag_commit"]
    run = api("/actions/runs/" + os.environ["GITHUB_RUN_ID"])
    assert run["event"] == "workflow_dispatch" and run["head_branch"] == "main"
    assert run["head_sha"] == os.environ["GITHUB_SHA"] and run["path"] == WORKFLOW
    assert run["head_repository"]["full_name"] == REPOSITORY
    trusted_run(manifest["candidate_run_id"], manifest["source_commit"])
    target = args.candidate / "publication-resume-provenance.json"
    if args.mode == "select":
        try:
            with urlopen(
                "https://pypi.org/pypi/collective-intelligence-overlay/0.4.1/json", timeout=30
            ):
                raise ValueError("0.4.1 already exists; refuse publication retry or overwrite")
        except HTTPError as error:
            assert error.code == 404
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as output:
            json.dump(provenance, output, indent=2, sort_keys=True)
            output.write("\n")
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write("reuse_run_id=" + manifest["candidate_run_id"] + "\n")
            output.write("production_run_id=\npretested_full=true\n")
    else:
        assert json.loads(target.read_bytes()) == provenance
        assert json.loads((args.candidate / "artifacts.json").read_bytes()) == manifest["artifacts"]
    print("immutable tag, original trusted native gate and actual recovery workflow verified")


if __name__ == "__main__":
    main()
