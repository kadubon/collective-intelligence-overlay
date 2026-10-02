"""Single runtime manifest for Actions, report gates and the documented target table."""

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def manifest():
    data = json.loads((ROOT / "scripts/runtime-matrix.json").read_text(encoding="utf-8"))
    assert data["scope"] == "full"
    assert len(data["python"]) == len(set(data["python"]))
    assert len({(r["os"], r["architecture"]) for r in data["runtimes"]}) == len(data["runtimes"])
    return data


def combinations():
    data = manifest()
    return [
        {**runtime, "python": patch, "scope": data["scope"]}
        for runtime in data["runtimes"]
        for patch in data["python"]
    ]


def table():
    rows = [
        "| OS | Native CPU | Runner | CPython patches | Required scope |",
        "| --- | --- | --- | --- | --- |",
    ]
    data = manifest()
    for runtime in data["runtimes"]:
        rows.append(
            f"| {runtime['os']} | {runtime['architecture']} | `{runtime['runner']}` | "
            f"{', '.join(data['python'])} | {data['scope']} |"
        )
    return "\n".join(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output", action="store_true")
    parser.add_argument("--write-docs", action="store_true")
    parser.add_argument("--check-docs", action="store_true")
    args = parser.parse_args()
    if args.github_output:
        data = manifest()
        outputs = {"minimum": data["python"][0], "latest": data["python"][-1]}
        outputs["cross"] = json.dumps(
            {"include": [{**r, "python": data["python"][0]} for r in data["runtimes"]]}
        )
        for name, system in (("linux", "Linux"), ("windows", "Windows"), ("macos", "Darwin")):
            outputs[name] = json.dumps(
                {
                    "include": [
                        r
                        for r in combinations()
                        if r["os"] == system
                        and (
                            os.environ.get("CIO_REPRESENTATIVE") != "true"
                            or r["python"] == data["python"][0]
                        )
                    ]
                }
            )
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            for name, value in outputs.items():
                output.write(f"{name}={value}\n")
    if args.write_docs or args.check_docs:
        path = ROOT / "docs/compatibility.md"
        start, end = "<!-- runtime-matrix:start -->", "<!-- runtime-matrix:end -->"
        content = path.read_text(encoding="utf-8")
        expected = start + "\n" + table() + "\n" + end
        if start not in content:
            assert args.write_docs, "runtime table missing"
            content = content + "\n\n" + expected + "\n"
        else:
            previous = content[content.index(start) : content.index(end) + len(end)]
            if args.check_docs:
                assert previous == expected, "runtime table differs from manifest"
            content = content.replace(previous, expected)
        if args.write_docs:
            path.write_text(content, encoding="utf-8")
    if not (args.github_output or args.write_docs or args.check_docs):
        print(json.dumps(combinations(), indent=2))


if __name__ == "__main__":
    main()
