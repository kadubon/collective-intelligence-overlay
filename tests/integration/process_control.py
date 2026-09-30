"""Stop only this test's child tree, including Windows uv venv launchers."""

import os
import subprocess


def stop_owned_process(process, *, kill=False):
    if process.poll() is None:
        if os.name == "nt":
            # A venv launcher can have a native Python child with the open sockets.
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=True,
                timeout=10,
                capture_output=True,
            )
        elif kill:
            process.kill()
        else:
            process.terminate()
    process.wait(timeout=10)
