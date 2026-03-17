# How-To: Re-run Failed Jobs

Re-run only the failed (or specific) jobs without resetting the entire workflow.

## Reset All Failed Jobs

```python
from torcpy.client import TorcClient
from torcpy.models.enums import JobStatus
from torcpy.models.job import JobUpdate
import asyncio

async def rerun_failed(workflow_id: int):
    async with TorcClient() as client:
        # Get all failed jobs
        result = await client.list_jobs(workflow_id, status=int(JobStatus.FAILED))
        failed_jobs = result["items"]
        print(f"Resetting {len(failed_jobs)} failed jobs...")

        for job in failed_jobs:
            await client.update_job(
                workflow_id,
                job["id"],
                JobUpdate(status=JobStatus.UNINITIALIZED),
            )

        # Re-initialize (rebuilds dep graph, marks newly-ready jobs)
        await client.initialize_workflow(workflow_id)
        print("Ready to run")

asyncio.run(rerun_failed(42))
```

Then run the worker again:

```console
torcpy workflows run 42
```

## Reset a Single Job

```console
# Via CLI — set status back to uninitialized (0)
torcpy jobs update <workflow_id> <job_id> --status 0
torcpy workflows initialize <workflow_id>
torcpy workflows run <workflow_id>
```

## Reset Terminated Jobs

Jobs that were `terminated` (walltime exceeded) can be reset the same way:

```python
result = await client.list_jobs(workflow_id, status=int(JobStatus.TERMINATED))
for job in result["items"]:
    await client.update_job(workflow_id, job["id"], JobUpdate(status=JobStatus.UNINITIALIZED))
```

## Reset the Whole Workflow

To start completely from scratch:

```console
torcpy workflows reset <workflow_id>
torcpy workflows run <workflow_id>
```

`reset` increments the `run_id` and returns all jobs to `uninitialized`.

## Preserve Completed Jobs

If you want to skip already-completed jobs when re-running, the current approach is to
leave them in `completed` status. During `initialize`, only `uninitialized` jobs are
processed — `completed` jobs are left as-is and won't be re-claimed.

!!! tip
    Only reset (`status=0`) the jobs you actually want to re-run. Completed jobs will
    remain completed and their dependents will already be resolved correctly.
