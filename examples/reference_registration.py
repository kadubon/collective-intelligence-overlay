"""Public registration entrypoint for the installed CSV reference application.

The implementation is packaged so the CLI demo and this example use the same
registrations. Application-owned registrations are also shown in document_application.py.
"""

from collective_intelligence_overlay.reference_bindings import register_reference

__all__ = ["register_reference"]
