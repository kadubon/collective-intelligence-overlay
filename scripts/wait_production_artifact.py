"""Wait for an already running formal report without accepting missing evidence."""

import argparse
import json
import os
import time
from urllib.request import Request, urlopen


def wait(run_id: str, maximum_seconds: int = 5400) -> None:
    if not run_id.isdigit():
        raise ValueError("numeric original run ID required")
    repository = os.environ["GITHUB_REPOSITORY"]
    if repository != "kadubon/collective-intelligence-overlay":
        raise ValueError("original repository required")
    base = f"https://api.github.com/repos/{repository}/actions/runs/{run_id}"
    headers = {"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"]}

    def read(suffix):
        with urlopen(Request(base + suffix, headers=headers), timeout=30) as response:
            return json.load(response)

    deadline = time.monotonic() + maximum_seconds
    print(f"Waiting for original formal report from run {run_id}", flush=True)
    while True:
        artifacts = read("/artifacts?per_page=100")["artifacts"]
        if any(row["name"] == "reports-production" and not row["expired"] for row in artifacts):
            print("Original formal report is available; assessment remains required", flush=True)
            return
        run = read("")
        if run["status"] == "completed":
            raise RuntimeError("original run completed without retained formal reports")
        production = [
            row for row in read("/jobs?per_page=100")["jobs"] if row["name"] == "production"
        ]
        if len(production) == 1 and production[0]["status"] == "completed":
            raise RuntimeError("original production job completed without retained formal reports")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                "original formal report did not become available within 5400 seconds"
            )
        time.sleep(min(60, remaining))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    wait(args.run_id)
