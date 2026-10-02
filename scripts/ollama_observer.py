"""Compatibility import for source-only protocol scripts; implementation is packaged."""

from collective_intelligence_overlay.adapters.inference_observer import (
    RawInferenceTransport,
    write_new,
)

__all__ = ["RawInferenceTransport", "write_new"]
