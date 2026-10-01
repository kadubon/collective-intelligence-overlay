"""Owned test process: shift the overlay's Python clock, never the system/DB clock."""

import argparse
import sys
from datetime import datetime, timedelta

from collective_intelligence_overlay import models
from collective_intelligence_overlay.cli import main


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offset-seconds", type=int, required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    if not -3600 <= args.offset_seconds <= 3600:
        raise ValueError("finite test clock offset required")

    class OffsetDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(seconds=args.offset_seconds)

    # All modules importing the public models.now function retain its reference;
    # that function reads this module's clock. No SDK internals are patched and
    # PostgreSQL clock_timestamp(), monotonic time and HTTP JWT verification stay real.
    models.datetime = OffsetDateTime
    sys.argv = ["collective-intelligence-overlay", "peer", "--config", args.config]
    return main()


if __name__ == "__main__":
    raise SystemExit(run())
