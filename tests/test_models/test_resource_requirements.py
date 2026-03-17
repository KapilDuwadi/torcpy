"""Tests for resource requirements parsing."""

from torcpy.models.resource_requirements import parse_memory_to_bytes, parse_runtime_to_seconds


def test_parse_memory_bytes():
    assert parse_memory_to_bytes("1k") == 1024
    assert parse_memory_to_bytes("1m") == 1024**2
    assert parse_memory_to_bytes("1g") == 1024**3
    assert parse_memory_to_bytes("2g") == 2 * 1024**3
    assert parse_memory_to_bytes("512m") == 512 * 1024**2
    assert parse_memory_to_bytes(None) is None


def test_parse_runtime_seconds():
    assert parse_runtime_to_seconds("PT30M") == 1800
    assert parse_runtime_to_seconds("PT2H") == 7200
    assert parse_runtime_to_seconds("PT1H30M") == 5400
    assert parse_runtime_to_seconds("P1DT0S") == 86400
    assert parse_runtime_to_seconds("PT30S") == 30
    assert parse_runtime_to_seconds(None) is None
