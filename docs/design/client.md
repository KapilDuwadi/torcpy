# Client Design

## Module Structure

```
src/torcpy/client/
├── api_client.py          # TorcClient — async HTTP client
├── workflow_spec.py       # WorkflowSpec + create_workflow_from_spec()
├── parameter_expansion.py # Parameter ranges, lists, Cartesian product
├── job_runner.py          # JobRunner — local parallel execution engine
├── resource_tracker.py    # ResourceTracker — CPU/memory/GPU accounting
└── async_command.py       # run_command() — non-blocking subprocess
```

## TorcClient

`TorcClient` wraps every REST endpoint with an async method. It uses `httpx.AsyncClient`
internally and supports both manual lifecycle management and use as an async context manager.

```python
# Context manager (recommended)
async with TorcClient(base_url="http://localhost:8080/torcpy/v1") as client:
    workflow = await client.create_workflow(CreateWorkflow(name="my-pipeline"))

# Manual lifecycle
client = TorcClient()
await client.__aenter__()
# ... use client ...
await client.__aexit__(None, None, None)
```

### Base URL Resolution

The client resolves its base URL in priority order:

1. `base_url` constructor argument
2. `TORCPY_API_URL` environment variable
3. Default: `http://localhost:8080/torcpy/v1`

### Error Handling

`httpx.HTTPStatusError` is raised for 4xx/5xx responses (via `response.raise_for_status()`).
Callers should handle:

- `404 Not Found` — resource does not exist
- `422 Unprocessable Entity` — validation error (response body has field-level details)
- `409 Conflict` — state conflict (e.g., canceling an already-completed workflow)

## WorkflowSpec

`WorkflowSpec` is a Pydantic model that represents the declarative format users write in YAML,
JSON, or JSON5 files.

```python
@classmethod
def from_file(cls, path: Path) -> "WorkflowSpec":
    # Dispatches on suffix: .yaml/.yml → PyYAML
    #                        .json5    → json5 library
    #                        .json     → stdlib json
```

### create_workflow_from_spec()

Translates a `WorkflowSpec` into live server resources in a fixed order:

```
WorkflowSpec
  │
  ├─► POST /workflows            → workflow_id
  ├─► POST /workflows/{id}/files (for each file in spec)
  ├─► POST /workflows/{id}/user_data
  ├─► POST /workflows/{id}/failure_handlers
  ├─► POST /workflows/{id}/schedulers
  └─► Job creation (two passes)
        Pass 1: create all jobs without depends_on → get job IDs
        Pass 2: for jobs with explicit depends_on:
                  resolve names → IDs, DELETE job, re-create with depends_on_job_ids
```

**Why two passes?** YAML specs use human-readable job names in `depends_on`. A job may depend on
another job defined later in the file. Two passes ensure all job IDs exist before resolving
cross-references.

## Parameter Expansion

Parameterized specs generate multiple job instances from a single `JobSpec` with a `parameters`
field.

```python
class ParameterValue:
    @staticmethod
    def parse(value: str | list) -> ParameterValue: ...
    def values(self) -> list[Any]: ...
```

### Supported Formats

| Format | Example | Result |
|---|---|---|
| Integer range | `"1:5"` | `[1, 2, 3, 4, 5]` |
| Range with step | `"0:100:10"` | `[0, 10, 20, ..., 100]` |
| Float range | `"0.0:1.0:0.25"` | `[0.0, 0.25, 0.5, 0.75, 1.0]` |
| List | `"[1, 5, 10]"` | `[1, 5, 10]` |
| String list | `"['a', 'b']"` | `['a', 'b']` |
| Literal | `42` | `[42]` |

### Expansion Modes

- **`cartesian`** (default): Cartesian product of all parameter lists
- **`zip`**: Element-wise pairing (all lists must have the same length)

### Template Substitution

```python
substitute_template("{lr:.4f}_batch{bs:03d}", {"lr": 0.001, "bs": 32})
# → "0.0010_batch032"
```

Substitution uses Python's `str.format_map()` with format specifiers — any valid Python format
spec works (`d`, `f`, `s`, `e`, `g`, `03d`, `.2f`, etc.).

## JobRunner

`JobRunner` drives local parallel execution. It polls the server for ready jobs, enforces resource
constraints, launches subprocesses, and reports results back to the server.

```python
config = JobRunnerConfig(
    workflow_id=42,
    output_dir=Path("output"),
    stdio_mode=StdioMode.SEPARATE,
    poll_interval=2.0,
    max_concurrent_jobs=8,
)
runner = JobRunner(client, config, resource_tracker)
await runner.run()
```

### Execution Loop

```
while workflow not terminal:
    jobs = await client.claim_next_jobs(workflow_id, n=slots_available)
    for job in jobs:
        task = asyncio.create_task(run_job(job))
        active_tasks.add(task)
    done, pending = await asyncio.wait(active_tasks, timeout=poll_interval)
    for task in done:
        result = task.result()
        await client.complete_job(workflow_id, job_id, result)
        resource_tracker.release(job.resource_requirements)
```

### Resource Accounting

Before claiming jobs, the runner checks `resource_tracker.can_fit()` to determine how many
concurrent slots are available. Resources are allocated on claim and released on completion.

### Shutdown

`JobRunner` installs `SIGINT`/`SIGTERM` handlers. On signal:

1. Stop claiming new jobs
2. Wait for all active tasks to complete
3. Return gracefully

## ResourceTracker

`ResourceTracker` maintains counts of available CPUs, memory (bytes), and GPUs:

```python
tracker = ResourceTracker.detect_local()  # auto-detects system resources
tracker = ResourceTracker(cpus=16, memory_bytes=64 * 1024**3, gpus=2)

if tracker.can_fit(job.resource_requirements):
    tracker.allocate(job.resource_requirements)
    # ... run job ...
    tracker.release(job.resource_requirements)
```

`detect_local()` uses `os.cpu_count()`, `psutil.virtual_memory()`, and CUDA device enumeration
(falls back to 0 if unavailable).

## AsyncCommand

`run_command()` launches a shell subprocess asynchronously:

```python
result = await run_command(
    command="python train.py --lr 0.001",
    stdout_path=Path("output/job_42.stdout"),
    stderr_path=Path("output/job_42.stderr"),
    walltime_seconds=3600.0,
)
```

Walltime enforcement uses `asyncio.wait_for()` wrapping `process.wait()`. On timeout, the process
group is killed with `SIGKILL` and the job is marked `terminated`.

### Stdio Modes

| StdioMode | Files Written |
|---|---|
| `separate` | `job_N.stdout` + `job_N.stderr` |
| `combined` | `job_N.log` (merged) |
| `no_stdout` | `job_N.stderr` only |
| `no_stderr` | `job_N.stdout` only |
| `none` | No files — output discarded |
