"""Gate pip-licenses output against reviewed expressions and scoped exceptions."""

import json
import sys

PERMISSIVE = {
    "3-Clause BSD License",
    "Apache Software License",
    "Apache Software License; BSD License",
    "Apache Software License; MIT License",
    "Apache-2.0",
    "Apache-2.0 OR BSD-2-Clause",
    "Apache-2.0 OR BSD-3-Clause",
    "BSD License",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC License (ISCL)",
    "MIT",
    "MIT License",
    "MIT No Attribution License (MIT-0)",
    "MIT-0",
    "PSF-2.0",
    "Python Software Foundation License",
}
EXCEPTIONS = {
    "numpy": {"BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0"},
    "certifi": {"Mozilla Public License 2.0 (MPL 2.0)"},
    "fqdn": {"Mozilla Public License 2.0 (MPL 2.0)"},
    "hypothesis": {"MPL-2.0"},
    "pathspec": {"Mozilla Public License 2.0 (MPL 2.0)"},
    "chardet": {"GNU Lesser General Public License v2 or later (LGPLv2+)"},
    "docutils": {"BSD License; GNU General Public License (GPL); Public Domain"},
}
rows = json.load(open(sys.argv[1], encoding="utf-8"))
unreviewed = [
    r["Name"]
    for r in rows
    if r["License"] not in PERMISSIVE
    and r["License"] not in EXCEPTIONS.get(r["Name"].lower(), set())
]
if unreviewed:
    raise SystemExit("unreviewed license metadata: " + ", ".join(unreviewed))
print(f"reviewed license metadata for {len(rows)} distributions; see docs/compatibility.md")
