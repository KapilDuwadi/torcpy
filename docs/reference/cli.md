# CLI Reference

## Global Options

| Option | Default | Description |
|---|---|---|
| `--url TEXT` | `$TORCPY_API_URL` or `http://localhost:8080/torcpy/v1` | Server URL |
| `-v, --verbose` | `false` | Enable debug logging |
| `--help` | | Show help and exit |

---

## `torcpy server run`

Start the TorcPy REST API server.

```console
torcpy server run [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--host TEXT` | `localhost` | Host to bind to |
| `--port INT` | `8080` | Port to listen on |
| `--db TEXT` | `torcpy.db` | SQLite database file path |

---

## `torcpy run`

Create a workflow from a spec file and run it locally, or run an existing workflow by ID.

```console
torcpy run SPEC_OR_ID [OPTIONS]
```

| Argument/Option | Description |
|---|---|
| `SPEC_OR_ID` | Path to a YAML/JSON spec file, or an integer workflow ID |
| `-o, --output-dir TEXT` | Directory for job stdout/stderr logs (default: `output`) |

---

## `torcpy submit`

Create a workflow from a spec file and initialize it (build dependency graph) without running.

```console
torcpy submit SPEC_OR_ID
```

---

## `torcpy workflows`

### `create`

```console
torcpy workflows create SPEC_FILE [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `SPEC_FILE` | | Path to YAML/JSON spec file (must exist) |
| `-f, --format {table,json}` | `table` | Output format |

### `list`

```console
torcpy workflows list [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `-f, --format {table,json}` | `table` | Output format |

### `get`

```console
torcpy workflows get WORKFLOW_ID [OPTIONS]
```

### `status`

```console
torcpy workflows status WORKFLOW_ID [OPTIONS]
```

Shows total job count and counts grouped by status.

### `run`

```console
torcpy workflows run WORKFLOW_ID [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `-o, --output-dir TEXT` | `output` | Directory for job logs |

### `initialize`

```console
torcpy workflows initialize WORKFLOW_ID
```

Builds the dependency graph (inserts implicit deps from files/user_data) and transitions
jobs to `ready` or `blocked`.

### `cancel`

```console
torcpy workflows cancel WORKFLOW_ID
```

Sets `is_canceled=true` and cancels all `uninitialized`, `blocked`, `ready`, and `pending` jobs.

### `reset`

```console
torcpy workflows reset WORKFLOW_ID
```

Returns all jobs to `uninitialized` and increments `run_id`.

### `delete`

```console
torcpy workflows delete WORKFLOW_ID
```

Deletes the workflow and all associated data (jobs, files, results, events) via cascade.

---

## `torcpy jobs`

### `list`

```console
torcpy jobs list WORKFLOW_ID [OPTIONS]
```

| Option | Description |
|---|---|
| `-s, --status INT` | Filter by status code (0–10) |
| `-f, --format {table,json}` | Output format |

### `get`

```console
torcpy jobs get WORKFLOW_ID JOB_ID [OPTIONS]
```

### `update`

```console
torcpy jobs update WORKFLOW_ID JOB_ID [OPTIONS]
```

| Option | Description |
|---|---|
| `-s, --status INT` | New status code |

---

## `torcpy reports`

### `summary`

```console
torcpy reports summary WORKFLOW_ID [OPTIONS]
```

Shows job status counts and total execution time.

### `results`

```console
torcpy reports results WORKFLOW_ID [OPTIONS]
```

Shows per-job execution metrics (return code, time, memory).
