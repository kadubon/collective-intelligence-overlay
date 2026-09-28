"""Check local documentation links and schemas derived from the public models."""

import argparse
import json
import re
from pathlib import Path

from collective_intelligence_overlay.models import Capability, Event, Evidence

parser = argparse.ArgumentParser()
parser.add_argument("--write-schemas", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
for model in (Capability, Evidence, Event):
    path = root / "src/collective_intelligence_overlay/schemas" / f"{model.__name__.lower()}.json"
    content = json.dumps(model.model_json_schema(), indent=2) + "\n"
    if args.write_schemas:
        path.parent.mkdir(exist_ok=True)
        path.write_text(content, encoding="utf-8")
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
