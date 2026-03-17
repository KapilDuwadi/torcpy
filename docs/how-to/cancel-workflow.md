# How-To: Cancel a Workflow

## Cancel via CLI

```console
torcpy workflows cancel <workflow_id>
```

This immediately:

1. Sets `workflow_status.is_canceled = true`
2. Transitions all `uninitialized`, `blocked`, `ready`, and `pending` jobs to `canceled`

!!! note "Running jobs are not interrupted"
    Jobs that are already `running` continue until they finish. Workers detect the cancellation
    flag on their next poll and stop claiming new jobs.

## Cancel via Python

```python
from torcpy.client import TorcClient

async with TorcClient() as client:
    await client.cancel_workflow(workflow_id=42)
```

## Check Status After Cancellation

```console
torcpy workflows status 42
```

```
Workflow 42
  Canceled: True
  Total jobs: 50
  Job status:
    completed: 23
    canceled: 27
```

## Resume After Cancellation

You cannot directly "un-cancel" a workflow, but you can reset and re-run it:

```console
torcpy workflows reset 42
torcpy workflows run 42
```

`reset` sets all jobs back to `uninitialized` and increments the `run_id`. The next `run`
call will re-initialize and re-execute only jobs that need to run.

!!! warning
    `reset` re-runs **all** jobs, including ones that previously completed. See
    [Re-run Failed Jobs](./rerun-failed-jobs.md) for a more targeted approach.
