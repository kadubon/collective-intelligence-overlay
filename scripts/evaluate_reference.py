"""Run a bounded matched comparison using the installed public overlay API."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from collective_intelligence_overlay.demo import initialize, run_demo


async def run(args):
    configs = initialize(args.directory, args.database_url, args.opa)
    result = await run_demo(args.directory, configs)
    result["unmeasured"] = ["long-term maintenance", "currency charges", "real-model quality"]
    (args.directory / "evaluation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument(
        "--database-url", default=os.environ.get("CIO_TEST_DATABASE_URL"), required=False
    )
    parser.add_argument("--opa", default=os.environ.get("CIO_OPA", "opa"))
    asyncio.run(run(parser.parse_args()))
