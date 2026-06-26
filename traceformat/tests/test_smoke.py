"""Smoke test: package is importable."""

import traceformat
from traceformat import models as tf


def test_import() -> None:
    assert traceformat.__doc__ is not None


def test_version_3_enum_value() -> None:
    """Version.field_3 enum member should exist with value "3"."""
    v = tf.Version("3")
    assert v.value == "3"


def test_pdu_discovery_enum_value() -> None:
    """Pdu.discovery enum member should exist with value "discovery"."""
    p = tf.Pdu("discovery")
    assert p.value == "discovery"


def test_request_with_empty_oids() -> None:
    """Request should accept empty oids list."""
    req = tf.Request(pdu=tf.Pdu("discovery"), request_id=1, oids=[])
    assert req.oids == []
