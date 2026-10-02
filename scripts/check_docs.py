"""Check local documentation links and schemas derived from the public models."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from collective_intelligence_overlay.bindings import ArtifactSpec, Binding
from collective_intelligence_overlay.config import Config
from collective_intelligence_overlay.models import (
    Capability,
    Event,
    Evidence,
    Opportunity,
    Proposal,
)

parser = argparse.ArgumentParser()
parser.add_argument("--write-schemas", action="store_true")
parser.add_argument("--write-cli-help", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
help_environment = {**os.environ, "COLUMNS": "80", "NO_COLOR": "1"}


def cli_help(*arguments):
    return subprocess.check_output(
        [sys.executable, "-m", "collective_intelligence_overlay.cli", *arguments, "--help"],
        text=True,
        encoding="utf-8",
        env=help_environment,
        timeout=20,
    )


main_help = cli_help()
commands = re.search(r"\{([a-z0-9,\s-]+)\}", main_help).group(1).replace("\n", "").split(",")
cli_reference = "Generated CLI help; exact help comes from your installed version.\n\n" + main_help
for command in commands:
    cli_reference += "\n" + cli_help(command.strip())
cli_path = root / "docs/cli-help.txt"
if args.write_cli_help:
    cli_path.write_text(cli_reference, encoding="utf-8", newline="\n")
else:
    saved = cli_path.read_text(encoding="utf-8")
    # argparse wrapping/color can differ across supported interpreters. Check
    # actual commands and flags, rather than requiring identical presentation.
    assert re.findall(r"--[a-z][a-z-]+", saved) == re.findall(r"--[a-z][a-z-]+", cli_reference)
    assert set(re.findall(r"collective-intelligence-overlay ([a-z-]+)", saved)) == set(
        re.findall(r"collective-intelligence-overlay ([a-z-]+)", cli_reference)
    )
for model in (Capability, Evidence, Event, Opportunity, Proposal, Binding, ArtifactSpec, Config):
    path = root / "src/collective_intelligence_overlay/schemas" / f"{model.__name__.lower()}.json"
    content = json.dumps(model.model_json_schema(), indent=2) + "\n"
    if args.write_schemas:
        path.parent.mkdir(exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    elif path.read_text(encoding="utf-8") != content:
        raise SystemExit(f"stale schema: {path}")
for path in [*root.glob("*.md"), *root.glob("docs/*.md"), *root.glob(".agents/skills/*/SKILL.md")]:
    for link in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
        if "://" in link or link.startswith("#"):
            continue
        target = (path.parent / link.split("#", 1)[0]).resolve()
        if not target.exists():
            raise SystemExit(f"broken local link: {path.name}: {link}")
print("documentation links and generated model schemas checked")
