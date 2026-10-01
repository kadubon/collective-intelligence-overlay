"""Real owned subprocess exit and deterministic public-tool race controls."""

import os
import subprocess
import sys

import process_control
import pytest


def test_owned_exit_between_poll_and_stop_is_positively_confirmed(monkeypatch, caplog):
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
    real_run = subprocess.run
    real_terminate = process.terminate

    def finished_before_taskkill(*args, **kwargs):
        assert process.wait(timeout=10) == 0
        return real_run(*args, **kwargs)

    def finished_before_signal():
        assert process.wait(timeout=10) == 0
        real_terminate()

    try:
        if os.name == "nt":
            monkeypatch.setattr(process_control.subprocess, "run", finished_before_taskkill)
        else:
            monkeypatch.setattr(process, "terminate", finished_before_signal)
        process_control.stop_owned_process(process)
        assert process.poll() == 0
        if os.name == "nt":
            assert "TASKKILL_RACE_CONFIRMED" in caplog.text
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)


def test_stop_failure_is_not_suppressed_for_a_live_owned_process(monkeypatch):
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])

    def refused_tool(command, **_):
        return subprocess.CompletedProcess(command, 1, b"", b"injected tool refusal")

    def refused_signal():
        raise PermissionError("injected signal refusal")

    try:
        with monkeypatch.context() as changes:
            if os.name == "nt":
                changes.setattr(process_control.subprocess, "run", refused_tool)
                exception = subprocess.CalledProcessError
            else:
                changes.setattr(process, "terminate", refused_signal)
                exception = PermissionError
            with pytest.raises(exception):
                process_control.stop_owned_process(process)
            assert process.poll() is None
    finally:
        process_control.stop_owned_process(process, kill=True)
