"""Child-only crash injection around the real CAS writer, never a product hook."""

import argparse
import os
import time
from pathlib import Path

import collective_intelligence_overlay.artifacts as module
from collective_intelligence_overlay.artifacts import Artifacts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("phase")
    parser.add_argument("ready", type=Path)
    args = parser.parse_args()
    artifacts = Artifacts(args.directory)

    def pause():
        args.ready.write_text(args.phase, encoding="utf-8")
        while True:
            time.sleep(0.05)

    create = module.tempfile.NamedTemporaryFile
    sync = os.fsync
    replace = os.replace

    def temporary(*positional, **keywords):
        file = create(*positional, **keywords)
        write = file.write

        def interrupted_write(value):
            if args.phase == "before-write":
                pause()
            if args.phase == "during-write":
                write(value[: len(value) // 2])
                file.flush()
                pause()
            return write(value)

        file.write = interrupted_write
        return file

    def interrupted_sync(descriptor):
        sync(descriptor)
        if args.phase == "after-fsync":
            pause()

    def interrupted_replace(source, target):
        if args.phase == "before-rename":
            pause()
        replace(source, target)
        if args.phase == "after-rename":
            pause()

    module.tempfile.NamedTemporaryFile = temporary
    os.fsync = interrupted_sync
    os.replace = interrupted_replace
    artifacts.put(b"finite original artifact" * 1000)


if __name__ == "__main__":
    main()
