# Python API Reference

## `TorcClient`

```python
from torcpy.client import TorcClient
```

The main async HTTP client. Use as an async context manager.

### Constructor

```python
TorcClient(
    base_url: str = "http://localhost:8080/torcpy/v1",
    timeout: float = 30.0,
)
```

### Methods

#### Health

| Method | Returns | Description |
|---|---|---|
| `await client.ping()` | `dict` | `{"status": "ok"}` |
| `await client.version()` | `dict` | `{"version": "..."}` |

#### Workflows

| Method | Returns | Description |
|---|---|---|
| `await client.create_workflow(body)` | `Workflow` | Create a new workflow |
| `await client.list_workflows(offset, limit)` | `dict` | Paginated list |
| `await client.get_workflow(workflow_id)` | `Workflow` | Get by ID |
| `await client.update_workflow(workflow_id, body)` | `Workflow` | Partial update |
| `await client.delete_workflow(workflow_id)` | `None` | Delete (cascades) |
| `await client.cancel_workflow(workflow_id)` | `dict` | Cancel |
| `await client.initialize_workflow(workflow_id)` | `dict` | Build dep graph |
| `await client.reset_workflow(workflow_id)` | `dict` | Reset all jobs |
| `await client.workflow_status(workflow_id)` | `dict` | Status summary |

#### Jobs

| Method | Returns | Description |
|---|---|---|
| `await client.create_job(workflow_id, body)` | `Job` | Create a job |
| `await client.list_jobs(workflow_id, status, offset, limit)` | `dict` | Paginated list |
| `await client.get_job(workflow_id, job_id)` | `Job` | Get by ID |
| `await client.update_job(workflow_id, job_id, body)` | `Job` | Partial update |
| `await client.delete_job(workflow_id, job_id)` | `None` | Delete |
| `await client.claim_next_jobs(workflow_id, count, compute_node_id, sort)` | `list[Job]` | Claim ready jobs |
| `await client.complete_job(workflow_id, job_id, status)` | `Job` | Complete (signals background task) |
| `await client.reset_job(workflow_id, job_id)` | `Job` | Reset to uninitialized |

#### Files, User Data, Results, etc.

See full method list in the source: `src/torcpy/client/api_client.py`.

---

## `WorkflowSpec`

```python
from torcpy.client import WorkflowSpec
```

### Class Methods

```python
spec = WorkflowSpec.from_file("pipeline.yaml")   # load from YAML, JSON, or JSON5
spec = WorkflowSpec(data_dict)                    # from Python dict
```

### Properties

| Attribute | Type | Description |
|---|---|---|
| `name` | `str` | Workflow name |
| `user` | `str \| None` | Owner |
| `jobs` | `list[JobSpec]` | Job definitions |
| `files` | `list[FileSpec]` | File definitions |
| `user_data` | `list[UserDataSpec]` | User data definitions |
| `schedulers` | `list[SchedulerSpec]` | Scheduler definitions |
| `failure_handlers` | `list[FailureHandlerSpec]` | Failure handler definitions |

---

## `create_workflow_from_spec`

```python
from torcpy.client import create_workflow_from_spec

wf_id = await create_workflow_from_spec(client, spec)
```

Creates all workflow components atomically. If any step fails, the workflow is deleted.

---

## `JobRunner`

```python
from torcpy.client import JobRunner
from torcpy.client.job_runner import JobRunnerConfig
```

### Constructor

```python
JobRunner(
    client: TorcClient,
    workflow_id: int,
    config: JobRunnerConfig | None = None,
)
```

### `JobRunnerConfig`

| Field | Default | Description |
|---|---|---|
| `poll_interval` | `2.0` | Seconds between polls |
| `max_parallel_jobs` | `0` | Max concurrent jobs (0 = unlimited) |
| `output_dir` | `"output"` | Directory for job logs |
| `stdio_mode` | `StdioMode.SEPARATE` | Stdout/stderr capture mode |
| `idle_timeout` | `0` | Seconds before idle exit (0 = no timeout) |
| `claim_batch_size` | `5` | Jobs to claim per poll |

### Methods

```python
stats = await runner.run()
# Returns {"completed": N, "failed": N, "canceled": N}
```

---

## `ResourceTracker`

```python
from torcpy.client.resource_tracker import ResourceTracker

tracker = ResourceTracker.detect_local()
print(tracker.total_cpus, tracker.available_cpus)
print(tracker.total_memory_bytes, tracker.available_memory_bytes)
print(tracker.total_gpus, tracker.available_gpus)
```

---

## Models

All models are Pydantic v2 classes in `torcpy.models`:

```python
from torcpy.models import (
    Workflow, WorkflowCreate, WorkflowUpdate,
    Job, JobCreate, JobUpdate,
    File, FileCreate, FileUpdate,
    UserData, UserDataCreate, UserDataUpdate,
    ResourceRequirements, ResourceRequirementsCreate,
    Result, ResultCreate,
    ComputeNode, ComputeNodeCreate,
    Event, EventCreate,
    FailureHandler, FailureHandlerCreate,
    LocalScheduler, LocalSchedulerCreate,
    SlurmScheduler, SlurmSchedulerCreate,
)
from torcpy.models.enums import JobStatus, StdioMode, EventSeverity
```
