"""Pytest configuration and shared fixtures."""

import json
from pathlib import Path

import jsonschema
import pytest


@pytest.fixture(scope="session")
def record_validator() -> jsonschema.Draft202012Validator:
    """Load the OIDTrace JSON Schema and return a validator for it."""
    schema_path = Path(__file__).parents[2] / "docs" / "trace-format.schema.json"
    schema = json.loads(schema_path.read_text())
    return jsonschema.Draft202012Validator(schema)
