"""Owned local Ollama and OS observations; no pull, global config or credentials."""

import asyncio
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from accumulation_application import DIGEST, MODEL

from collective_intelligence_overlay.adapters.inference_observer import write_new
from collective_intelligence_overlay.bindings import fingerprint


def server_environment_digest(environment):
    """Pin model/backend/proxy overrides without republishing private values or paths."""
    keys = {
        "CUDA_VISIBLE_DEVICES",
        "GGML_VK_VISIBLE_DEVICES",
        "GPU_DEVICE_ORDINAL",
        "HIP_VISIBLE_DEVICES",
        "HSA_OVERRIDE_GFX_VERSION",
        "ROCR_VISIBLE_DEVICES",
        "LLAMA_ARG_FIT",
        "LLAMA_ARG_FIT_TARGET",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
    }
    return fingerprint(
        {k: v for k, v in environment.items() if k.startswith("OLLAMA_") or k in keys}
    )


def runtime_contract(manifest):
    # The original /api/show includes local FROM/DRAFT and upstream imatrix
    # paths. Pin the same public home-path projection used by the archive,
    # preserving blob names, every directive and all other model metadata.
    from prepare_gemma_public import PATH_TRANSFORMATIONS

    show_raw = json.dumps(manifest["show"]).encode()
    for pattern, replacement, _ in PATH_TRANSFORMATIONS:
        show_raw = re.sub(pattern, replacement, show_raw)
    show = json.loads(show_raw)
    # /api/show renders the parameter map in process-dependent line order.
    # Normalize only unique named entries; preserve every complete value line.
    parameters = show["parameters"]
    if not isinstance(parameters, str):
        raise ValueError("model parameter listing must be text")
    lines = parameters.split("\n") if parameters else []
    names = [re.fullmatch(r"([a-z][a-z0-9_]*)\s+\S.*", line) for line in lines]
    if any(name is None for name in names) or len({name[1] for name in names}) != len(lines):
        raise ValueError("model parameter listing requires unique complete named entries")
    show["parameters"] = sorted(lines)
    selected = next(
        m for m in manifest["tags"]["models"] if m["name"] == manifest["requested_model"]
    )
    return {
        "ollama_version": manifest["version"]["version"],
        "ollama_binary_sha256": manifest["ollama_binary_sha256"],
        "python": manifest["hardware"]["python"],
        "dependencies": manifest["hardware"]["selected_dependencies"],
        "operating_system": manifest["operating_system"],
        "machine": manifest["machine"],
        "hardware_native": manifest["hardware"].get("native"),
        "owned_server_settings": manifest["settings"],
        "owned_server_environment_sha256": manifest["owned_server_environment_sha256"],
        "selected_model_digest": selected["digest"],
        "selected_model_details": selected["details"],
        "model_show_projection_schema": "home-path-unique-parameter-order-v2",
        "selected_model_show_public_projection_sha256": fingerprint(show),
    }


def check_metadata_observations(rows, manifest, maximum):
    if not rows or [r["index"] for r in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("missing or duplicated owned-server metadata observations")
    if len(rows) > maximum or manifest["metadata_observation_call_cap"] != maximum:
        raise ValueError("owned-server metadata budget changed or exceeded")
    before = manifest["metadata_observations_before_inference"]
    if type(before) is not int or not 5 <= before <= len(rows):
        raise ValueError("missing owned-server startup observations")
    for r in rows:
        elapsed = r["client_elapsed_seconds"]
        if (
            (r["method"], r["path"])
            not in {
                ("GET", "/api/version"),
                ("GET", "/api/tags"),
                ("GET", "/api/ps"),
                ("POST", "/api/show"),
            }
            or isinstance(elapsed, bool)
            or not isinstance(elapsed, int | float)
            or not math.isfinite(elapsed)
            or elapsed < 0
            or r["raw_inventory_or_private_model_path_republished"] is not False
        ):
            raise ValueError("invalid original owned-server metadata observation")
        if r["response_bytes"] is not None:
            if (
                type(r["response_bytes"]) is not int
                or not 0 <= r["response_bytes"] <= 1048576
                or not isinstance(r["native_response_sha256"], str)
                or len(r["native_response_sha256"]) != 64
            ):
                raise ValueError("metadata response hash or byte bound changed")
    startup = [(r["method"], r["path"]) for r in rows[:before] if r["status"] == 200]
    for required in (
        ("GET", "/api/version"),
        ("GET", "/api/tags"),
        ("GET", "/api/ps"),
        ("POST", "/api/show"),
    ):
        if required not in startup:
            raise ValueError("required original startup model observation is missing")
    if [(r["method"], r["path"]) for r in rows[before:]] != [
        ("GET", "/api/ps"),
        ("GET", "/api/version"),
    ]:
        raise ValueError("required owned-server final observations changed")
    return {
        "startup_and_readiness_calls": before,
        "final_calls": len(rows) - before,
        "total_calls": len(rows),
        "cap": maximum,
    }


class ProcessObserver:
    """Collect actual cumulative CPU/RSS, retaining errors as missing samples."""

    def __init__(self, output, maximum_seconds, interval=5):
        self.path = Path(output)
        self.maximum = maximum_seconds
        self.interval = interval
        self.stop_event = threading.Event()
        self.roots = {os.getpid()}
        self.started = time.monotonic()
        self.thread = None
        self.stream = self.path.open("x", encoding="utf-8")

    def sample(self):
        item = {
            "at": datetime.now(UTC).isoformat(),
            "elapsed_seconds": time.monotonic() - self.started,
            "roots": sorted(self.roots),
            "energy_joules": None,
            "gpu_counters": None,
        }
        try:
            if sys_platform_windows():
                shell = shutil.which("pwsh") or shutil.which("powershell")
                roots = ",".join(str(x) for x in sorted(self.roots))
                code = (
                    "$ErrorActionPreference='Stop'; $taskProcesses=Get-CimInstance Win32_Process; "
                )
                code += f"$taskIds=[Collections.Generic.HashSet[int]]::new(); @({roots}) | "
                code += "ForEach-Object { [void]$taskIds.Add($_) }; "
                code += "do { $taskChanged=$false; foreach($taskP in $taskProcesses) { "
                code += "if ($taskIds.Contains([int]$taskP.ParentProcessId) -and "
                code += "$taskIds.Add([int]$taskP.ProcessId)) { $taskChanged=$true } } } "
                code += "while($taskChanged); @($taskProcesses | Where-Object { "
                code += "$taskIds.Contains([int]$_.ProcessId) } | ForEach-Object { "
                code += "$taskP=$_; $taskValue=Get-Process -Id $_.ProcessId -ErrorAction "
                code += "SilentlyContinue; if($taskValue) { @{ pid=[int]$taskP.ProcessId; "
                code += "parent_pid=[int]$taskP.ParentProcessId; name=$taskP.Name; "
                code += "cpu_seconds=$taskValue.TotalProcessorTime.TotalSeconds; "
                code += "rss_bytes=$taskValue.WorkingSet64; "
                code += "started_at=$taskValue.StartTime.ToUniversalTime().ToString('o') } } }) "
                code += "| ConvertTo-Json -Depth 4 -Compress"
                value = subprocess.run(
                    [shell, "-NoProfile", "-NonInteractive", "-Command", code],
                    capture_output=True,
                    timeout=10,
                    check=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                item["processes"] = json.loads(value.stdout)
                item["method"] = (
                    "Win32_Process ancestry; Get-Process cumulative CPU and working set"
                )
            else:
                from run_production_experiment import process_sample, subtree

                snapshot, vanished = process_sample()
                item["processes"] = subtree(snapshot, tuple(self.roots))
                item["vanished_during_sample"] = vanished
                item["method"] = "native Linux proc ancestry/cumulative CPU/RSS"
            item["status"] = "measured"
        except Exception as error:
            item.update(status="unavailable", error_type=type(error).__name__)
        item["sample_completed_seconds"] = time.monotonic() - self.started
        self.stream.write(json.dumps(item) + "\n")
        self.stream.flush()

    def start(self):
        self.sample()  # Completes before the owned model server starts.

        def loop():
            while not self.stop_event.wait(self.interval):
                if time.monotonic() - self.started >= self.maximum:
                    break
                self.sample()

        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=15)
            if self.thread.is_alive():
                raise RuntimeError("resource observer did not physically stop")
        self.stream.close()


def sys_platform_windows():
    return os.name == "nt"


def hardware_profile():
    result = {
        "platform": platform.platform(),
        "python": sys.version,
        "implementation": platform.python_implementation(),
        "selected_dependencies": {
            name: importlib.metadata.version(name)
            for name in (
                "agent-framework-core",
                "agent-framework-ollama",
                "ollama",
                "httpx",
                "pydantic",
                "sqlalchemy",
                "numpy",
                "scipy",
            )
        },
        "short_lived_descendant_cpu": None,
        "CPU_aggregation_limit": "polling can miss short-lived subprocesses; no zero imputation",
        "shared_WSL_PostgreSQL_CPU": None,
    }
    if sys_platform_windows():
        code = "@{cpu=@(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,"
        code += "NumberOfLogicalProcessors); system=Get-CimInstance Win32_ComputerSystem | "
        code += "Select-Object TotalPhysicalMemory; gpu=@(Get-CimInstance Win32_VideoController | "
        code += "Select-Object Name,DriverVersion,AdapterRAM); os=Get-CimInstance "
        code += "Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture} "
        code += "| ConvertTo-Json -Depth 5 -Compress"
        shell = shutil.which("pwsh") or shutil.which("powershell")
        data = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-Command", code],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        result["native"] = json.loads(data.stdout)
    return result


class OwnedOllama:
    def __init__(self, home, output, *, port=11443, context=8192, metadata_cap=160):
        self.home, self.output = Path(home), Path(output)
        self.port, self.context = port, context
        self.process, self.log = None, None
        self.host = f"http://127.0.0.1:{port}"
        if type(metadata_cap) is not int or not 1 <= metadata_cap <= 256:
            raise ValueError("finite owned-server metadata call cap required")
        self.metadata_cap, self.metadata_calls = metadata_cap, 0

    async def metadata(self, client, method, path, **options):
        if self.metadata_calls >= self.metadata_cap:
            raise ValueError("owned-server metadata observation cap")
        self.metadata_calls += 1
        record = {
            "index": self.metadata_calls,
            "method": method,
            "path": path,
            "at": datetime.now(UTC).isoformat(),
            "status": None,
            "response_bytes": None,
            "native_response_sha256": None,
            "error_type": None,
            "raw_inventory_or_private_model_path_republished": False,
        }
        started = time.monotonic()
        try:
            response = await client.request(method, path, **options)
            record.update(
                status=response.status_code,
                response_bytes=len(response.content),
                native_response_sha256=hashlib.sha256(response.content).hexdigest(),
            )
            if len(response.content) > 1048576:
                raise ValueError("owned-server metadata response byte cap")
            return response
        except BaseException as error:
            record["error_type"] = type(error).__name__
            raise
        finally:
            record["client_elapsed_seconds"] = time.monotonic() - started
            with (self.output / "model-metadata-calls.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps(record, allow_nan=False) + "\n")

    async def start(self):
        self.home.mkdir()  # Never reuse another server home.
        with socket.socket() as check:
            check.bind(("127.0.0.1", self.port))
        binary = shutil.which("ollama")
        if binary is None:
            raise ValueError("installed Ollama binary required; no download is permitted")
        hardware = await asyncio.to_thread(hardware_profile)
        settings = {
            "OLLAMA_HOST": f"127.0.0.1:{self.port}",
            "OLLAMA_NO_CLOUD": "1",
            "OLLAMA_NUM_PARALLEL": "1",
            "OLLAMA_MAX_QUEUE": "4",
            "OLLAMA_MAX_LOADED_MODELS": "1",
            "OLLAMA_CONTEXT_LENGTH": str(self.context),
            "OLLAMA_KEEP_ALIVE": "5m",
            "OLLAMA_DEBUG": "1",
        }
        self.log = (self.home / "server.log").open("xb")
        process_environment = {**os.environ, **settings}
        self.process = await asyncio.to_thread(
            subprocess.Popen,
            [binary, "serve"],
            env=process_environment,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys_platform_windows() else 0,
        )
        write_new(
            self.home / "owner.json",
            {
                "pid": self.process.pid,
                "parent_pid": os.getpid(),
                "binary": binary,
                "settings": settings,
                "host": self.host,
                "started_at": datetime.now(UTC).isoformat(),
                "pull_performed": False,
                "existing_server_config_changed": False,
            },
        )
        async with httpx.AsyncClient(base_url=self.host, trust_env=False, timeout=5) as client:
            async with asyncio.timeout(30):
                while True:
                    if self.process.poll() is not None:
                        raise RuntimeError("owned Ollama exited")
                    try:
                        if (await self.metadata(client, "GET", "/api/version")).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.2)
            values = {
                "version": (await self.metadata(client, "GET", "/api/version")).json(),
                "tags": (await self.metadata(client, "GET", "/api/tags")).json(),
                "show": (
                    await self.metadata(client, "POST", "/api/show", json={"model": MODEL})
                ).json(),
                "ps_before": (await self.metadata(client, "GET", "/api/ps")).json(),
            }
        selected = next((m for m in values["tags"]["models"] if m["name"] == MODEL), None)
        if selected is None or selected["digest"] != DIGEST:
            raise ValueError("exact installed gemma4:e4b required; no pull or alternate")
        values.update(
            hardware=hardware,
            ollama_binary_sha256=hashlib.sha256(
                await asyncio.to_thread(Path(binary).read_bytes)
            ).hexdigest(),
            host=self.host,
            requested_model=MODEL,
            digest=DIGEST,
            settings=settings,
            owned_server_environment_sha256=server_environment_digest(process_environment),
            operating_system=platform.platform(),
            processor=platform.processor(),
            machine=platform.machine(),
            energy_joules=None,
            gpu_compute_counters=None,
            global_model_config_changed=False,
            weights_republished=False,
            metadata_observation_call_cap=self.metadata_cap,
            metadata_observations_before_inference=self.metadata_calls,
        )
        write_new(self.output / "model-manifest.json", values)
        return values

    async def close(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            try:
                async with httpx.AsyncClient(base_url=self.host, trust_env=False, timeout=5) as c:
                    write_new(
                        self.output / "model-after.json",
                        {
                            "ps_after": (await self.metadata(c, "GET", "/api/ps")).json(),
                            "version_after": (await self.metadata(c, "GET", "/api/version")).json(),
                        },
                    )
            finally:
                # Stops only the known owned process tree, not the user's server.
                from production_mesh import stop_process

                await asyncio.to_thread(stop_process, self.process, kill=True)
        self.log.close()
