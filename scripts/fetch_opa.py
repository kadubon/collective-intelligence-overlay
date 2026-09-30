"""Developer wrapper around the distribution's explicit, verified OPA installer."""

import os
from pathlib import Path

from collective_intelligence_overlay.opa_install import install_opa


def main() -> None:
    try:
        print(install_opa(Path(".local/bin") / ("opa.exe" if os.name == "nt" else "opa")))
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
