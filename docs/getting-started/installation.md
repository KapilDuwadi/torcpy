# Installation

TorcPy requires **Python 3.11+**.

## Using uv (Recommended)

[uv](https://github.com/astral-sh/uv) is the recommended tool for installing TorcPy. It is
significantly faster than pip and handles virtual environments automatically.

```console
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create a project and add TorcPy
uv add torcpy

# Or install globally into a virtual environment
uv pip install torcpy
```

## Using pip

```console
pip install torcpy
```

## Development Installation

To install from source with development dependencies:

```console
git clone https://github.com/your-org/torcpy
cd torcpy
uv pip install -e ".[dev]"
```

## Verify Installation

```console
torcpy --version
torcpy --help
```

## Optional Dependencies

| Feature | Package | Notes |
|---|---|---|
| JSON5 spec files | `json5` | Included by default |
| YAML spec files | `pyyaml` | Included by default |

## System Requirements

| Component | Requirement |
|---|---|
| Python | 3.11 or later |
| SQLite | 3.35+ (bundled with Python) |
| OS | Linux, macOS, Windows |

!!! note "No external services required"
    TorcPy uses SQLite — no PostgreSQL, Redis, or message broker required. The server
    and database run as a single process.

## Next Steps

- [Quick Start (Local)](./quick-start-local.md) — Run your first workflow
