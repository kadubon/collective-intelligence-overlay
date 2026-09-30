"""Source launcher for the installed document reference application."""

import sys

from collective_intelligence_overlay.starter import documents as implementation

if __name__ == "__main__":
    implementation.main()
else:
    sys.modules[__name__] = implementation
