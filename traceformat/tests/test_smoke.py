"""Smoke test: package is importable."""

import traceformat


def test_import() -> None:
    assert traceformat.__doc__ is not None
