"""Smoke test: package is importable and schema fixture is functional."""

from __future__ import annotations

import json

# pyrefly: ignore [untyped-import]
from jsonschema import Draft202012Validator

import oidtrace


def test_import() -> None:
    assert oidtrace.__doc__ is not None


def test_record_validator_rejects_empty(record_validator: Draft202012Validator) -> None:
    """An empty object must not validate against the trace schema."""
    errors = list(record_validator.iter_errors(json.loads("{}")))
    assert len(errors) > 0
