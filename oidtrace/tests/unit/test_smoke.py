"""Smoke tests for the oidtrace package."""

import oidtrace


def test_package_has_docstring() -> None:
    """The package must have a module docstring."""
    assert oidtrace.__doc__ is not None
    assert len(oidtrace.__doc__) > 0
