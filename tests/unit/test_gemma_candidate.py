"""An installer assertion cannot hide changed or source-shadowed core code."""

import hashlib
import importlib.machinery
import importlib.util
import json
import sys
import types
import zipfile
from pathlib import Path

import pytest

from collective_intelligence_overlay.models import Event, Subject, now


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    path = Path(__file__).parents[2] / "scripts/check_gemma_candidate.py"
    spec = importlib.util.spec_from_file_location("tested_gemma_candidate", path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    repository, prefix = tmp_path / "repository", tmp_path / "interpreter"
    repository.mkdir()
    site = prefix / "Lib/site-packages"
    package = site / checker.PACKAGE
    package.mkdir(parents=True)
    metadata = "collective_intelligence_overlay-0.4.2.dist-info/METADATA"
    entries = {
        checker.PACKAGE + "/__init__.py": b'__version__ = "0.4.2"\n',
        checker.PACKAGE + "/models.py": b"ORIGINAL = True\n",
        checker.PACKAGE + "/policies/default.rego": b"package cio\n",
        metadata: b"Name: collective-intelligence-overlay\nVersion: 0.4.2\n",
    }
    wheel = repository / "candidate.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, raw in entries.items():
            archive.writestr(name, raw)
            installed = site / name
            installed.parent.mkdir(parents=True, exist_ok=True)
            installed.write_bytes(raw)
    artifact = {"path": "candidate.whl", "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()}
    direct = {"archive_info": {"hashes": {"sha256": artifact["sha256"]}}}
    distribution = types.SimpleNamespace(
        version="0.4.2",
        read_text=lambda _name: json.dumps(direct),
        locate_file=lambda name: site / name,
    )
    monkeypatch.setattr(checker.importlib.metadata, "distribution", lambda _name: distribution)
    monkeypatch.setattr(sys, "prefix", str(prefix))
    for name in tuple(sys.modules):
        if name == checker.PACKAGE or name.startswith(checker.PACKAGE + "."):
            monkeypatch.delitem(sys.modules, name)
    module = types.ModuleType(checker.PACKAGE)
    module.__file__ = str(package / "__init__.py")
    module.__path__ = [str(package)]
    monkeypatch.setitem(sys.modules, checker.PACKAGE, module)
    return types.SimpleNamespace(
        checker=checker,
        repository=repository,
        package=package,
        module=module,
        direct=direct,
        distribution=distribution,
        artifact=artifact,
        entries=entries,
        wheel=wheel,
    )


def test_original_installed_bytes_and_actual_origin_are_checked(candidate):
    c = candidate
    result = c.checker.installed_candidate(c.repository, c.artifact)
    assert result["installed_wheel_sha256"] == c.artifact["sha256"]
    assert result["original_package_file_sha256"] == {
        name: hashlib.sha256(raw).hexdigest()
        for name, raw in c.entries.items()
        if name.startswith(c.checker.PACKAGE + "/")
    }
    assert result["imported_module_origins"][c.checker.PACKAGE] == c.module.__file__
    assert result["editable"] is False


@pytest.mark.parametrize("target", ["original", "wheel", "package", "missing", "late", "PASS"])
def test_each_owner_candidate_proof_binds_original_bytes_before_execution(candidate, target):
    c = candidate
    package = {
        name: hashlib.sha256(raw).hexdigest()
        for name, raw in c.entries.items()
        if name.startswith(c.checker.PACKAGE + "/")
    }
    protocol = {"installed_wheel": {**c.artifact, "package_file_sha256": package}}
    body = {
        "wheel_sha256": c.artifact["sha256"],
        "version": "0.4.2",
        "original_package_file_sha256": package,
        "package_within_actual_interpreter_prefix": True,
        "all_loaded_package_modules_from_candidate": True,
        "editable": False,
        "inspection_scope": "trusted-host bytes/origins; no attestation",
    }
    observed = now()
    event = Event(
        id="candidate-installed-runtime",
        issuer="producer",
        subject=Subject(id="study-installed-candidate", version="1", digest="a" * 64),
        action="verification",
        task_id="startup",
        attempt_id="startup",
        correlation_id="startup",
        occurred_at=observed,
    )
    signed = {("event", "producer", event.id): event}
    if target == "wheel":
        body["wheel_sha256"] = "b" * 64
    elif target == "package":
        body["original_package_file_sha256"] = {}
    elif target == "missing":
        signed.clear()
    elif target == "late":
        signed["event", "producer", "model-early"] = Event(
            id="model-early",
            issuer="producer",
            subject=event.subject,
            action="verification",
            task_id="task",
            attempt_id="task",
            correlation_id="task",
            occurred_at=observed.replace(year=observed.year - 1),
        )
    elif target == "PASS":
        signed["event", "producer", event.id] = event.model_copy(update={"outcome": "PASS"})
    artifacts = {("producer", event.subject.digest): json.dumps(body).encode()}
    if target == "original":
        c.checker.check_candidate_observations(protocol, signed, artifacts, ("producer",))
    else:
        with pytest.raises((ValueError, KeyError)):
            c.checker.check_candidate_observations(protocol, signed, artifacts, ("producer",))


@pytest.mark.parametrize("member", ["models.py", "policies/default.rego"])
def test_matching_direct_url_cannot_hide_modified_package(candidate, member):
    c = candidate
    (c.package / member).write_bytes(b"changed")
    with pytest.raises(ValueError, match="package bytes"):
        c.checker.installed_candidate(c.repository, c.artifact)


def test_matching_bytes_cannot_hide_source_tree_import(candidate):
    c = candidate
    source = c.repository / "src" / c.checker.PACKAGE
    source.mkdir(parents=True)
    (source / "__init__.py").write_bytes((c.package / "__init__.py").read_bytes())
    c.module.__file__, c.module.__path__ = str(source / "__init__.py"), [str(source)]
    with pytest.raises(ValueError, match="source tree shadows"):
        c.checker.installed_candidate(c.repository, c.artifact)


def test_individual_loaded_core_module_cannot_escape(candidate, monkeypatch):
    c = candidate
    source = c.repository / "different_models.py"
    source.write_bytes((c.package / "models.py").read_bytes())
    foreign = types.ModuleType(c.checker.PACKAGE + ".models")
    foreign.__file__ = str(source)
    monkeypatch.setitem(sys.modules, foreign.__name__, foreign)
    with pytest.raises(ValueError, match="imported core module"):
        c.checker.installed_candidate(c.repository, c.artifact)


@pytest.mark.parametrize("kind", ["original", "foreign", "extra", "empty", "executable", "loader"])
def test_only_original_archive_backed_namespace_is_accepted(candidate, monkeypatch, kind):
    c = candidate
    # policies is a namespace directory backed by the original packaged rego.
    name = c.checker.PACKAGE + ".policies"
    namespace = types.ModuleType(name)
    original = str(c.package / "policies")
    locations = [original]
    if kind == "foreign":
        locations = [str(c.repository / "foreign")]
    elif kind == "extra":
        locations.append(str(c.repository / "foreign"))
    elif kind == "empty":
        name = c.checker.PACKAGE + ".absent"
        locations = [str(c.package / "absent")]
    namespace.__path__ = locations
    loader = importlib.machinery.NamespaceLoader(name, locations, importlib.machinery.PathFinder)
    namespace.__spec__ = importlib.util.spec_from_loader(name, loader=loader, is_package=True)
    namespace.__spec__.submodule_search_locations = locations
    if kind == "executable":
        namespace.__spec__.origin = "invented-module"
    elif kind == "loader":
        namespace.__spec__.loader = object()
    monkeypatch.setitem(sys.modules, name, namespace)
    if kind == "original":
        result = c.checker.installed_candidate(c.repository, c.artifact)
        assert result["imported_namespace_locations"][name] == original
    else:
        with pytest.raises(ValueError, match="core namespace"):
            c.checker.installed_candidate(c.repository, c.artifact)


def test_unregistered_package_module_is_rejected(candidate):
    c = candidate
    (c.package / "backdoor.py").write_bytes(b"extra")
    with pytest.raises(ValueError, match="unexpected installed package file"):
        c.checker.installed_candidate(c.repository, c.artifact)


def test_missing_package_file_is_rejected(candidate):
    c = candidate
    (c.package / "models.py").unlink()
    with pytest.raises(ValueError, match="missing or redirected"):
        c.checker.installed_candidate(c.repository, c.artifact)


@pytest.mark.parametrize("provenance", ["editable", "wrong_hash", "wrong_version"])
def test_candidate_provenance_is_required(candidate, provenance):
    c = candidate
    if provenance == "editable":
        c.direct["dir_info"] = {"editable": True}
    elif provenance == "wrong_hash":
        c.direct["archive_info"]["hashes"]["sha256"] = "0" * 64
    else:
        c.distribution.version = "0.4.1"
    with pytest.raises(ValueError):
        c.checker.installed_candidate(c.repository, c.artifact)


@pytest.mark.parametrize("path", ["../candidate.whl", "C:/candidate.whl", "/candidate.whl"])
def test_preregistered_candidate_path_is_relative(candidate, path):
    c = candidate
    with pytest.raises(ValueError, match="repository-relative"):
        c.checker.installed_candidate(c.repository, {**c.artifact, "path": path})


def test_installed_metadata_is_part_of_candidate_identity(candidate):
    c = candidate
    metadata = next(name for name in c.entries if name.endswith("/METADATA"))
    c.distribution.locate_file(metadata).write_bytes(b"Name: different\nVersion: 0.4.2\n")
    with pytest.raises(ValueError, match="installed distribution metadata"):
        c.checker.installed_candidate(c.repository, c.artifact)


def test_changed_wheel_rejected_before_installer_assertion(candidate):
    c = candidate
    with c.wheel.open("ab") as output:
        output.write(b"changed")
    with pytest.raises(ValueError, match="candidate wheel changed"):
        c.checker.installed_candidate(c.repository, c.artifact)


def test_different_interpreter_install_is_rejected(candidate, monkeypatch):
    c = candidate
    monkeypatch.setattr(sys, "prefix", str(c.repository))
    with pytest.raises(ValueError, match="actual interpreter"):
        c.checker.installed_candidate(c.repository, c.artifact)


def test_unsafe_wheel_member_is_rejected(candidate):
    c = candidate
    with zipfile.ZipFile(c.wheel, "a") as archive:
        archive.writestr("../outside.py", b"unregistered")
    c.artifact["sha256"] = hashlib.sha256(c.wheel.read_bytes()).hexdigest()
    c.direct["archive_info"]["hashes"]["sha256"] = c.artifact["sha256"]
    with pytest.raises(ValueError, match="unsafe candidate archive member"):
        c.checker.installed_candidate(c.repository, c.artifact)


def test_original_wheel_version_cannot_be_overridden_by_installer_metadata(candidate):
    c = candidate
    metadata = next(name for name in c.entries if name.endswith("/METADATA"))
    with zipfile.ZipFile(c.wheel, "w") as archive:
        for name, raw in c.entries.items():
            archive.writestr(name, raw.replace(b"0.4.2", b"0.4.1") if name == metadata else raw)
    c.artifact["sha256"] = hashlib.sha256(c.wheel.read_bytes()).hexdigest()
    c.direct["archive_info"]["hashes"]["sha256"] = c.artifact["sha256"]
    with pytest.raises(ValueError, match="wheel metadata"):
        c.checker.installed_candidate(c.repository, c.artifact)


def test_actual_uv_hashed_local_url_form_retains_all_byte_checks(candidate):
    c = candidate
    c.direct["archive_info"] = {}
    c.direct["url"] = c.wheel.as_uri() + "#sha256=" + c.artifact["sha256"]
    result = c.checker.installed_candidate(c.repository, c.artifact)
    assert result["installer_hash_representation"] == "exact_local_file_url_sha256_fragment"
    assert len(result["original_package_file_sha256"]) == 3
    (c.package / "models.py").write_bytes(b"changed")
    with pytest.raises(ValueError, match="package bytes"):
        c.checker.installed_candidate(c.repository, c.artifact)


@pytest.mark.parametrize("case", ["missing", "different_file", "remote", "wrong", "conflict"])
def test_absent_conflicting_or_different_file_hash_provenance_is_rejected(candidate, case):
    c = candidate
    c.direct["archive_info"] = {}
    c.direct["url"] = c.wheel.as_uri() + "#sha256=" + c.artifact["sha256"]
    if case == "missing":
        c.direct["url"] = c.wheel.as_uri()
    elif case == "different_file":
        c.direct["url"] = (
            (c.repository / "different.whl").as_uri() + "#sha256=" + c.artifact["sha256"]
        )
    elif case == "remote":
        c.direct["url"] = "https://example.invalid/candidate.whl#sha256=" + c.artifact["sha256"]
    elif case == "wrong":
        c.direct["url"] = c.wheel.as_uri() + "#sha256=" + "0" * 64
    else:
        c.direct["archive_info"] = {"hashes": {"sha256": c.artifact["sha256"]}}
        c.direct["url"] = c.wheel.as_uri() + "#sha256=" + "0" * 64
    with pytest.raises(ValueError):
        c.checker.installed_candidate(c.repository, c.artifact)
