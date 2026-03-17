# Debugging Workflows

## Enable Debug Logging

```console
torcpy --verbose workflows status 42
torcpy --verbose run pipeline.yaml
```

Or set the log level in Python:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Server SQL Debug Logging

To see every SQL query the server executes, set the `aiosqlite` logger:

```python
import logging
logging.getLogger("aiosqlite").setLevel(logging.DEBUG)
```

Or run the server with debug logging:

```console
PYTHONPATH=src python -c "
import logging, uvicorn
logging.basicConfig(level=logging.DEBUG)
from torcpy.server.app import create_app
uvicorn.run(create_app(), log_level='debug')
"
```

## Inspect the Database Directly

The SQLite database is a standard file you can inspect with any SQLite tool:

```bash
sqlite3 torcpy.db

# List all workflows
SELECT id, name, user FROM workflow;

# Count jobs by status
SELECT status, COUNT(*) FROM job WHERE workflow_id=1 GROUP BY status;

# Find stuck pending jobs
SELECT id, name, status FROM job WHERE status=3 AND workflow_id=1;

# Check unblocking queue
SELECT id, name FROM job WHERE status IN (5,6,7,8) AND unblocking_processed=0;
```

## Common Issues

### Jobs stuck in `pending`

A job is `pending` when it has been claimed by a worker but not yet completed. This can
happen if a worker crashes mid-execution.

**Fix:** Reset stuck pending jobs:

```python
from torcpy.models.enums import JobStatus
from torcpy.models.job import JobUpdate

result = await client.list_jobs(workflow_id, status=int(JobStatus.PENDING))
for job in result["items"]:
    await client.update_job(workflow_id, job["id"], JobUpdate(status=JobStatus.READY))
```

### Blocked jobs never becoming ready

**Check:**

1. Are their dependencies actually completing?
2. Is the background unblock task running? (check server logs)
3. Are there circular dependencies? (all jobs in the cycle stay blocked)

```bash
# Check the unblocking queue in SQLite
sqlite3 torcpy.db "
SELECT j.id, j.name, j.status, j.unblocking_processed
FROM job j
WHERE j.workflow_id = 1 AND j.status IN (5,6,7,8)
  AND j.unblocking_processed = 0;
"
```

### "Database is locked" errors

SQLite is optimized for single-writer, many-reader usage. If you see lock errors:

- Ensure you're not running multiple server processes against the same DB file.
- The server uses WAL mode and busy-timeout (5s) to handle concurrent access.

### Worker exits immediately

Check the server is running and reachable:

```console
torcpy --url http://localhost:8080/torcpy/v1 server run  # should already be running
curl http://localhost:8080/torcpy/v1/ping
```
