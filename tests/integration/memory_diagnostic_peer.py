"""Owned Linux diagnostic launcher of the unchanged normally installed CLI."""

import argparse
import gc
import json
import signal
import ssl
import sys
import tracemalloc
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--snapshots", type=Path, required=True)
    args = parser.parse_args()
    args.snapshots.mkdir(mode=0o700, exist_ok=False)
    tracemalloc.start(5)
    number = 0
    baseline = None

    def snapshot(signum, _frame):
        nonlocal number, baseline
        collected = gc.collect() if signum == signal.SIGUSR2 else None
        objects = gc.get_objects()
        types = Counter(type(item).__name__ for item in objects).most_common(20)
        ssl_count = sum(isinstance(item, ssl.SSLContext) for item in objects)
        # A diagnostic list must not itself retain every live object's graph.
        del objects
        current = tracemalloc.take_snapshot()
        if baseline is None:
            baseline = current
        report = {
            "explicit_diagnostic_gc": collected,
            "gc_counts": gc.get_count(),
            "tracked_types": types,
            "ssl_contexts": ssl_count,
            "python_traced_bytes": tracemalloc.get_traced_memory(),
            "python_allocations_are_rss": False,
            "largest_allocations": [str(stat) for stat in current.statistics("lineno")[:20]],
            "allocation_changes_from_first_snapshot": [
                str(stat) for stat in current.compare_to(baseline, "lineno")[:30]
            ],
        }
        (args.snapshots / f"{number:02}.json").write_text(json.dumps(report, indent=2))
        number += 1

    signal.signal(signal.SIGUSR1, snapshot)
    signal.signal(signal.SIGUSR2, snapshot)
    sys.argv = ["collective-intelligence-overlay", "peer", "--config", args.config]
    from collective_intelligence_overlay.cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
