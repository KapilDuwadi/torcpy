"""Tests for enums."""

from torcpy.models.enums import JobStatus


def test_job_status_values():
    assert JobStatus.UNINITIALIZED == 0
    assert JobStatus.COMPLETED == 5
    assert JobStatus.PENDING_FAILED == 10


def test_job_status_is_terminal():
    assert JobStatus.COMPLETED.is_terminal()
    assert JobStatus.FAILED.is_terminal()
    assert JobStatus.CANCELED.is_terminal()
    assert not JobStatus.RUNNING.is_terminal()
    assert not JobStatus.READY.is_terminal()
    assert not JobStatus.BLOCKED.is_terminal()


def test_job_status_is_active():
    assert JobStatus.PENDING.is_active()
    assert JobStatus.RUNNING.is_active()
    assert not JobStatus.COMPLETED.is_active()
    assert not JobStatus.READY.is_active()
