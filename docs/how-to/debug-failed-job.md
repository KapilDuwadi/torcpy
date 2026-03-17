# How-To: Debug a Failed Job

## 1. Find Failed Jobs

```console
torcpy jobs list <workflow_id> --status 6
```

## 2. Inspect a Specific Job

```console
torcpy jobs get <workflow_id> <job_id>
```

```
Job 47: process_data_batch_023
  Status: failed
  Command: python process.py --batch 23
  Priority: 0
  Depends on: [12]
```

## 3. Check Execution Results

```console
torcpy reports results <workflow_id> --format json | python -m json.tool
```

Look for:

- `return_code` — non-zero indicates the command failed
- `exec_time_minutes` — was it killed by walltime?
- `status` — `"failed"` vs `"completed"`

## 4. Read Job Logs

By default, TorcPy saves stdout and stderr for each job in the output directory:

```
output/
  job_47.stdout
  job_47.stderr
```

```console
cat output/job_47.stderr
```

If you ran with `--output-dir /path/to/logs`:

```console
cat /path/to/logs/job_47.stderr
```

## 5. Re-run the Job Manually

To reproduce the failure:

```console
# Get the exact command
torcpy jobs get <workflow_id> <job_id> --format json | python -c "import sys,json; print(json.load(sys.stdin)['command'])"

# Run it directly
python process.py --batch 23
```

## 6. Reset and Retry the Job

After fixing the issue:

```console
# Reset just this one job back to uninitialized
torcpy jobs update <workflow_id> <job_id> --status 0

# Re-initialize and run
torcpy workflows initialize <workflow_id>
torcpy workflows run <workflow_id>
```

Or reset all failed jobs at once via the Python client:

```python
from torcpy.client import TorcClient
from torcpy.models.enums import JobStatus
from torcpy.models.job import JobUpdate

async with TorcClient() as client:
    result = await client.list_jobs(workflow_id, status=JobStatus.FAILED)
    for job in result["items"]:
        await client.update_job(
            workflow_id,
            job["id"],
            JobUpdate(status=JobStatus.UNINITIALIZED),
        )
    await client.initialize_workflow(workflow_id)
```

## Common Failure Causes

| Symptom | Likely Cause |
|---|---|
| `return_code: 1` | Script error — check stderr |
| `return_code: 137` | OOM kill (memory limit exceeded) |
| `return_code: -1` | Walltime exceeded |
| Job stuck in `pending` | Worker crashed before completing the job |
| `pending_failed` status | Failure handler couldn't match the exit code |

## Next Steps

- [How-To: Re-run Failed Jobs](./rerun-failed-jobs.md)
- [Concepts: Job States](../concepts/job-states.md)
