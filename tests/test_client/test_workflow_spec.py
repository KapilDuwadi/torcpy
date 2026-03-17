"""Tests for workflow spec parsing."""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from torcpy.client.workflow_spec import WorkflowSpec


def test_parse_yaml_spec(tmp_path: Path):
    spec_data = {
        "name": "test-workflow",
        "user": "tester",
        "jobs": [
            {"name": "job1", "command": "echo hello"},
            {"name": "job2", "command": "echo world", "depends_on": ["job1"]},
        ],
        "files": [
            {"name": "input.txt", "path": "/data/input.txt"},
        ],
    }
    spec_file = tmp_path / "test.yaml"
    spec_file.write_text(yaml.dump(spec_data))

    spec = WorkflowSpec.from_file(spec_file)
    assert spec.name == "test-workflow"
    assert len(spec.jobs) == 2
    assert spec.jobs[1].depends_on == ["job1"]
    assert len(spec.files) == 1


def test_parse_json_spec(tmp_path: Path):
    spec_data = {
        "name": "json-wf",
        "jobs": [
            {
                "name": "step1",
                "command": "ls -la",
                "resource_requirements": {"num_cpus": 4, "memory": "2g"},
            },
        ],
    }
    spec_file = tmp_path / "test.json"
    spec_file.write_text(json.dumps(spec_data))

    spec = WorkflowSpec.from_file(spec_file)
    assert spec.name == "json-wf"
    assert spec.jobs[0].resource_requirements is not None
    assert spec.jobs[0].resource_requirements.num_cpus == 4
    assert spec.jobs[0].resource_requirements.memory == "2g"


def test_parameterized_jobs(tmp_path: Path):
    spec_data = {
        "name": "param-wf",
        "jobs": [
            {
                "name": "job_{i}",
                "command": "echo {i}",
                "parameters": {"i": "1:3"},
            },
        ],
    }
    spec_file = tmp_path / "test.yaml"
    spec_file.write_text(yaml.dump(spec_data))

    spec = WorkflowSpec.from_file(spec_file)
    assert len(spec.jobs) == 1
    assert spec.jobs[0].parameters == {"i": "1:3"}
