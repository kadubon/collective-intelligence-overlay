"""Download actual published files and compare their bytes with the tested candidate."""

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

parser = argparse.ArgumentParser()
parser.add_argument("--version", required=True)
parser.add_argument("--hash-file", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--report", type=Path, required=True)
args = parser.parse_args()
expected = json.loads(args.hash_file.read_text(encoding="utf-8"))
assert len(expected) == 2 and all(name.endswith((".whl", ".tar.gz")) for name in expected)
request = urllib.request.Request(
    f"https://pypi.org/pypi/collective-intelligence-overlay/{args.version}/json",
    headers={"Cache-Control": "no-cache"},
)
with urllib.request.urlopen(request, timeout=60) as response:
    metadata = json.load(response)
assert metadata["info"]["version"] == args.version
assert metadata["info"]["requires_python"] == ">=3.12"
files = metadata["urls"]
assert {file["filename"]: file["digests"]["sha256"] for file in files} == expected
args.output.mkdir(parents=True, exist_ok=True)
actual = {}
for file in files:
    url = urlsplit(file["url"])
    assert url.scheme == "https" and url.hostname == "files.pythonhosted.org"
    assert file["filename"] == Path(file["filename"]).name
    with urllib.request.urlopen(file["url"], timeout=60) as response:
        data = response.read()
    assert (
        len(data) == file["size"] and hashlib.sha256(data).hexdigest() == expected[file["filename"]]
    )
    target = args.output / file["filename"]
    if target.exists():
        assert target.read_bytes() == data, "refuse to replace a different release file"
    else:
        with target.open("xb") as stream:
            stream.write(data)
    actual[file["filename"]] = hashlib.sha256(data).hexdigest()
report = {
    "version": args.version,
    "index": "https://pypi.org/simple",
    "requires_python": metadata["info"]["requires_python"],
    "artifacts": actual,
}
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
