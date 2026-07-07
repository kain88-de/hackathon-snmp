"""Smoke test: package is importable."""

import traceformat
from traceformat import models as tf


def test_import() -> None:
    assert traceformat.__doc__ is not None


def test_request_with_empty_oids() -> None:
    """Request should accept empty oids list."""
    req = tf.Request(pdu=tf.Pdu("discovery"), request_id=1, oids=[])
    assert req.oids == []
