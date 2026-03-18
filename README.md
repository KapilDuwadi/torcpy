# TorcPy

[![CI](https://github.com/KapilDuwadi/torcpy/actions/workflows/ci.yml/badge.svg)](https://github.com/KapilDuwadi/torcpy/actions/workflows/ci.yml)

Distributed workflow orchestration for Python. Define jobs in YAML, track dependencies, and run pipelines locally or on Slurm — backed by SQLite and a REST API.

## Install

```bash
pip install torcpy
```

Requires Python 3.11+.

## Quick Start

```bash
# Start the server
torcpy server start

# Submit a workflow
torcpy workflow submit pipeline.yaml

# Watch progress
torcpy workflow status <workflow-id>
```

## Features

- Declarative YAML/JSON workflow definitions with automatic dependency resolution
- Parameter expansion — `"1:100"`, `"[0.001, 0.01, 0.1]"`, Cartesian product or zip
- Resource-aware scheduling (CPU, memory, GPU)
- REST API with typed async Python client
- Rich CLI output via `rich-click`

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src tests
```

## Docs

Full documentation at [torcpy.readthedocs.io](https://torcpy.readthedocs.io).

## License

MIT
