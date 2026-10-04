"""Seeded differential fuzz harness for the rfc5322 parser.

This package is **dev/test-only**.  It is never imported by the shipped
``rfc5322`` package and adds no runtime dependency: the third-party reference
(``email_validator``) is pulled in on demand via ``uv run --with``.

Layout
------
``corpus``
    Deterministic, seeded corpus generator (hand-written cases + a
    byte-level mutation fuzzer).
``references``
    Thin adapters over independent parsers (CPython stdlib and
    ``email_validator``).
``report``
    Runs the corpus against every reference and buckets the divergences.
``run``
    Command-line entry point (``python -m fuzz.run``).
"""

from __future__ import annotations

__all__ = ["corpus", "references", "report"]

SEED = 5322
