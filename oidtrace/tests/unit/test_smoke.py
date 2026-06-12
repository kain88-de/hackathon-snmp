"""Smoke test: package is importable and schema fixture is functional."""

from __future__ import annotations

import json

from jsonschema import Draft202012Validator

import oidtrace


def test_import() -> None:
    assert oidtrace.__doc__ is not None


def test_record_validator_fixture(record_validator: Draft202012Validator) -> None:
    """The session fixture returns a working validator against the trace schema."""
    # A minimal valid header record should satisfy the schema.
    # We just check the validator is wired up (schema loaded, instance is correct type).
    assert isinstance(record_validator, Draft202012Validator)


def test_record_validator_rejects_empty(record_validator: Draft202012Validator) -> None:
    """An empty object must not validate against the trace schema."""
    errors = list(record_validator.iter_errors(json.loads("{}")))
    assert len(errors) > 0
