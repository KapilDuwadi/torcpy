# How-To: Track Workflow Status

## Get a Status Summary

```console
torcpy workflows status <workflow_id>
```

Output:

```
Workflow 42
  Run ID: 0
  Canceled: False
  Total jobs: 101
  Job status:
    completed: 87
    running: 6
    pending: 2
    ready: 5
    blocked: 1
```

## List All Jobs

```console
torcpy jobs list <workflow_id>
```

Filter by status (use the integer code):

```console
# Show only failed jobs (status=6)
torcpy jobs list <workflow_id> --status 6

# Show only running jobs (status=4)
torcpy jobs list <workflow_id> --status 4
```

## Get JSON Output

All commands support `--format json`:

```console
torcpy workflows status 42 --format json
torcpy jobs list 42 --format json | python -m json.tool
```

## Continuous Monitoring (shell loop)

```bash
while true; do
    clear
    torcpy workflows status 42
    sleep 5
done
```

## Python Client

```python
import asyncio
from torcpy.client import TorcClient

async def monitor(workflow_id: int):
    async with TorcClient() as client:
        while True:
            status = await client.workflow_status(workflow_id)
            counts = status["job_status_counts"]
            total = status["total_jobs"]
            done = counts.get("completed", 0) + counts.get("failed", 0)

            print(f"Progress: {done}/{total}")
            print(f"  running={counts.get('running',0)}")
            print(f"  failed={counts.get('failed',0)}")

            if done == total:
                break

            await asyncio.sleep(5)

asyncio.run(monitor(42))
```

## Job Status Codes

| Code | Name |
|:---:|---|
| 0 | uninitialized |
| 1 | blocked |
| 2 | ready |
| 3 | pending |
| 4 | running |
| 5 | completed |
| 6 | failed |
| 7 | canceled |
| 8 | terminated |
| 9 | disabled |
| 10 | pending_failed |

See [Job States](../concepts/job-states.md) for the full reference.
