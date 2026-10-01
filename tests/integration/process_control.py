"""Stop only this test's child tree, including Windows uv venv launchers."""

import logging
import os
import subprocess


def stop_owned_process(process, *, kill=False):
    if process.poll() is None:
        if os.name == "nt":
            # A venv launcher can have a native Python child with the open sockets.
            result = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                timeout=10,
                capture_output=True,
            )
            if result.returncode:
                # The exact owned Popen handle may have completed between poll
                # and taskkill. A live target still makes every tool error fail.
                if process.poll() is None:
                    result.check_returncode()
                logging.getLogger(__name__).warning(
                    "TASKKILL_RACE_CONFIRMED pid=%s tool_exit=%s process_exit=%s",
                    process.pid,
                    result.returncode,
                    process.returncode,
                )
        elif kill:
            process.kill()
        else:
            process.terminate()
    process.wait(timeout=10)
