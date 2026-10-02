"""Check that confirmation imports the exact noneditable candidate wheel.

This is a pre-inference check, not model or installed native gate evidence.
Inspect original wheel package bytes and actual imported module origins instead
of treating an installer direct_url assertion alone as executable identity.
"""

import hashlib
import importlib
import importlib.machinery
import importlib.metadata
import json
import sys
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlsplit
from urllib.request import url2pathname

PACKAGE = "collective_intelligence_overlay"
DISTRIBUTION = "collective-intelligence-overlay"


def installed_candidate(root, artifact):
    root = Path(root).resolve()
    relative = PurePosixPath(artifact["path"])
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or "\\" in artifact["path"]
        or ":" in artifact["path"]
        or relative.suffix != ".whl"
    ):
        raise ValueError("candidate path must be repository-relative")
    original_path = root / Path(*relative.parts)
    wheel = original_path.resolve()
    if not wheel.is_relative_to(root) or original_path.is_symlink():
        raise ValueError("candidate wheel is outside the declared repository")
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != artifact["sha256"]:
        raise ValueError("exact preregistered candidate wheel changed")
    distribution = importlib.metadata.distribution(DISTRIBUTION)
    direct = json.loads(distribution.read_text("direct_url.json") or "{}")
    if direct.get("dir_info", {}).get("editable") or distribution.version != "0.4.2":
        raise ValueError("confirmation requires the actual noneditable 0.4.2 candidate")
    archive_hash = direct.get("archive_info", {}).get("hashes", {}).get("sha256")
    origin = urlsplit(direct.get("url", ""))
    fragments = parse_qs(origin.fragment, strict_parsing=True)
    fragment_hash = fragments.get("sha256", [])
    if archive_hash is not None and archive_hash != artifact["sha256"]:
        raise ValueError("installed candidate archive provenance changed")
    if fragment_hash and fragment_hash != [artifact["sha256"]]:
        raise ValueError("conflicting candidate URL fragment hash")
    if archive_hash is None and (
        origin.scheme != "file"
        or origin.netloc not in {"", "localhost"}
        or origin.query
        or fragments != {"sha256": [artifact["sha256"]]}
        or Path(url2pathname(origin.path)).resolve() != wheel
    ):
        raise ValueError("installed candidate lacks exact hashed local-wheel provenance")
    initial = Path(distribution.locate_file(PACKAGE + "/__init__.py"))
    package_root = initial.resolve().parent
    if not package_root.is_relative_to(Path(sys.prefix).resolve()):
        raise ValueError("installed candidate must belong to the actual interpreter")
    expected, package_files = {}, {}
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 10000:
            raise ValueError("ambiguous or oversized candidate archive")
        if sum(item.file_size for item in archive.infolist()) > 64 * 1024 * 1024:
            raise ValueError("oversized candidate archive")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                raise ValueError("unsafe candidate archive member")
        metadata_names = [n for n in names if n.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise ValueError("candidate distribution metadata is ambiguous")
        metadata_raw = archive.read(metadata_names[0])
        metadata = BytesParser().parsebytes(metadata_raw)
        if metadata["Name"] != DISTRIBUTION or metadata["Version"] != "0.4.2":
            raise ValueError("candidate wheel metadata differs from the registered version")
        if Path(distribution.locate_file(metadata_names[0])).read_bytes() != metadata_raw:
            raise ValueError("installed distribution metadata differs from candidate wheel")
        for name in names:
            if not name.startswith(PACKAGE + "/") or name.endswith("/"):
                continue
            info = archive.getinfo(name)
            if (
                info.file_size > 32 * 1024 * 1024
                or (info.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError("unsafe or oversized candidate package file")
            actual = Path(distribution.locate_file(name))
            if (
                actual.is_symlink()
                or not actual.resolve().is_relative_to(package_root)
                or not actual.is_file()
            ):
                raise ValueError("missing or redirected installed candidate file")
            digest = hashlib.sha256(archive.read(name)).hexdigest()
            if hashlib.sha256(actual.read_bytes()).hexdigest() != digest:
                raise ValueError("installed package bytes differ from candidate wheel")
            expected[actual.resolve()] = digest
            package_files[name] = digest
    if initial.resolve() not in expected:
        raise ValueError("candidate lacks its import package")
    for path in package_root.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path.resolve() not in expected:
            raise ValueError("unexpected installed package file outside candidate wheel")
    package = importlib.import_module(PACKAGE)
    if Path(package.__file__).resolve() != initial.resolve() or [
        Path(p).resolve() for p in package.__path__
    ] != [package_root]:
        raise ValueError("source tree shadows the installed candidate package")
    imported, namespaces = {}, {}
    for name, module in tuple(sys.modules.items()):
        if module is None or not (name == PACKAGE or name.startswith(PACKAGE + ".")):
            continue
        origin = getattr(module, "__file__", None)
        if origin is None:
            # adapters is a real PEP 420 namespace in the installed wheel.
            # Require its single exact archive-backed directory, never a
            # foreign search location or an invented executable module.
            namespace = package_root.joinpath(*name.split(".")[1:])
            locations = [Path(p).resolve() for p in getattr(module, "__path__", ())]
            spec = getattr(module, "__spec__", None)
            if (
                spec is None
                or not isinstance(spec.loader, importlib.machinery.NamespaceLoader)
                or spec.origin is not None
                or spec.submodule_search_locations is None
                or locations != [namespace]
                or [Path(p).resolve() for p in spec.submodule_search_locations] != locations
                or namespace.is_symlink()
                or not namespace.is_dir()
                or not any(path.is_relative_to(namespace) for path in expected)
                or (namespace / "__init__.py").exists()
            ):
                raise ValueError("imported core namespace is outside candidate package bytes")
            namespaces[name] = str(namespace)
            continue
        if origin is None or Path(origin).resolve() not in expected:
            raise ValueError("imported core module is outside candidate package bytes")
        imported[name] = str(Path(origin).resolve())
    return {
        "installed_wheel_sha256": artifact["sha256"],
        "version": distribution.version,
        "interpreter": sys.executable,
        "interpreter_prefix": sys.prefix,
        "package_root": str(package_root),
        "original_package_file_sha256": package_files,
        "imported_module_origins": imported,
        "imported_namespace_locations": namespaces,
        "editable": False,
        "installer_hash_representation": "archive_info"
        if archive_hash is not None
        else "exact_local_file_url_sha256_fragment",
    }


def check_candidate_observations(protocol, signed, artifacts, owners):
    """Check each original owner startup observation; this is host evidence, not attestation."""
    expected = {
        "wheel_sha256": protocol["installed_wheel"]["sha256"],
        "version": "0.4.2",
        "original_package_file_sha256": protocol["installed_wheel"]["package_file_sha256"],
        "package_within_actual_interpreter_prefix": True,
        "all_loaded_package_modules_from_candidate": True,
        "editable": False,
        "inspection_scope": "trusted-host bytes/origins; no attestation",
    }
    for owner in owners:
        event = signed["event", owner, "candidate-installed-runtime"]
        if (
            event.subject.id != "study-installed-candidate"
            or event.subject.version != "1"
            or event.action != "verification"
            or event.outcome is not None
            or event.task_id != "startup"
            or event.attempt_id != "startup"
            or json.loads(artifacts[owner, event.subject.digest]) != expected
        ):
            raise ValueError("owner lacks the exact installed candidate startup observation")
        if any(
            record.occurred_at < event.occurred_at
            for (kind, issuer, _), record in signed.items()
            if kind == "event"
            and issuer == owner
            and (record.execution is not None or record.id.startswith("model-"))
        ):
            raise ValueError("candidate inspection was recorded after original execution")
