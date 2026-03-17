"""Tests for CLI main module."""

from click.testing import CliRunner

from torcpy.cli.main import cli

runner = CliRunner()


def test_app_help():
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "TorcPy" in result.output


def test_workflows_help():
    result = runner.invoke(cli, ["workflows", "--help"])
    assert result.exit_code == 0
    assert "create" in result.output
    assert "list" in result.output


def test_jobs_help():
    result = runner.invoke(cli, ["jobs", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output


def test_server_help():
    result = runner.invoke(cli, ["server", "--help"])
    assert result.exit_code == 0
    assert "run" in result.output
