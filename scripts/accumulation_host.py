"""Owned local Ollama and OS observations; no pull, global config or credentials."""

import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
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

                snapshot = process_sample()
                item["processes"] = subtree(snapshot, tuple(self.roots))
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
    def __init__(self, home, output, *, port=11443, context=8192):
        self.home, self.output = Path(home), Path(output)
        self.port, self.context = port, context
        self.process, self.log = None, None
        self.host = f"http://127.0.0.1:{port}"

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
        self.process = await asyncio.to_thread(
            subprocess.Popen,
            [binary, "serve"],
            env={**os.environ, **settings},
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
                        if (await client.get("/api/version")).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.2)
            values = {
                "version": (await client.get("/api/version")).json(),
                "tags": (await client.get("/api/tags")).json(),
                "show": (await client.post("/api/show", json={"model": MODEL})).json(),
                "ps_before": (await client.get("/api/ps")).json(),
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
            operating_system=platform.platform(),
            processor=platform.processor(),
            machine=platform.machine(),
            energy_joules=None,
            gpu_compute_counters=None,
            global_model_config_changed=False,
            weights_republished=False,
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
                            "ps_after": (await c.get("/api/ps")).json(),
                            "version_after": (await c.get("/api/version")).json(),
                        },
                    )
            finally:
                # Stops only the known owned process tree, not the user's server.
                from production_mesh import stop_process

                await asyncio.to_thread(stop_process, self.process, kill=True)
        self.log.close()
