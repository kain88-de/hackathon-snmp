"""Shared pytest fixtures for the oidtrace test suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
# pyrefly: ignore [untyped-import]
from jsonschema import Draft202012Validator


@pytest.fixture(scope="session")
def record_validator() -> Draft202012Validator:
    """JSON Schema Draft 2020-12 validator over the canonical trace-format schema.

    Used to belt-and-braces validate produced records against the schema,
    independently of the pydantic models.
    """
    schema_path = Path(__file__).parents[2] / "docs" / "trace-format.schema.json"
    schema = json.loads(schema_path.read_text())
    return Draft202012Validator(schema)
