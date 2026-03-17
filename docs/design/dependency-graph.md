# Dependency Graph

## Overview

TorcPy supports two kinds of job dependencies:

- **Explicit**: declared directly in the workflow spec via `depends_on`
- **Implicit**: inferred automatically from shared files and user data

Both kinds are stored in the same `job_depends_on` table. The server treats them identically at
runtime — the distinction only matters during the `initialize` phase when the graph is built.

## Explicit Dependencies

Declared in the spec using job names:

```yaml
jobs:
  - name: preprocess
    command: python preprocess.py

  - name: train
    command: python train.py
    depends_on:
      - preprocess

  - name: evaluate
    command: python evaluate.py
    depends_on:
      - train
```

During `create_workflow_from_spec()`, names are resolved to job IDs in a two-pass process:

1. **Pass 1**: All jobs are created without `depends_on` to get their IDs
2. **Pass 2**: Jobs with `depends_on` are deleted and re-created with `depends_on_job_ids`

```
job_depends_on
  upstream_job_id  │  downstream_job_id
  ─────────────────┼───────────────────
        1          │        2          (preprocess → train)
        2          │        3          (train → evaluate)
```

## Implicit File Dependencies

When two jobs share a file — one as output, one as input — the server automatically inserts a
dependency between them during `initialize`.

```yaml
files:
  - name: preprocessed_data
    path: /data/preprocessed.parquet

jobs:
  - name: preprocess
    command: python preprocess.py
    output_files: [preprocessed_data]

  - name: train
    command: python train.py
    input_files: [preprocessed_data]
```

The server queries:

```sql
-- Find all (producer, consumer) pairs via shared files
SELECT DISTINCT
    pj.id AS upstream_job_id,
    cj.id AS downstream_job_id
FROM job_file jf_out
JOIN job_file jf_in ON jf_out.file_id = jf_in.file_id
JOIN job pj ON jf_out.job_id = pj.id
JOIN job cj ON jf_in.job_id = cj.id
WHERE jf_out.is_output = 1
  AND jf_in.is_output = 0
  AND pj.workflow_id = ?
  AND cj.workflow_id = ?
  AND pj.id != cj.id
```

These are inserted into `job_depends_on` as implicit rows (same table, same effect).

## User Data Dependencies

The same implicit dependency logic applies to `user_data`:

```yaml
user_data:
  - name: model_weights
    key: weights_v2

jobs:
  - name: train
    command: python train.py
    output_user_data: [model_weights]

  - name: serve
    command: python serve.py
    input_user_data: [model_weights]
```

## Initialization Algorithm

`POST /workflows/{id}/initialize` runs the following algorithm:

```
1. Insert all implicit file dependencies
2. Insert all implicit user_data dependencies
3. Skip duplicates (explicit deps may overlap with implicit ones)

4. Compute ready set:
   SELECT id FROM job j
   WHERE j.workflow_id = ?
     AND j.status = 0  -- uninitialized
     AND NOT EXISTS (
       SELECT 1 FROM job_depends_on d
       JOIN job upstream ON d.upstream_job_id = upstream.id
       WHERE d.downstream_job_id = j.id
         AND upstream.status != 5  -- not completed
     )

5. Mark jobs with no pending upstream dependencies → READY (status=2)
6. Mark remaining uninitialized jobs → BLOCKED (status=1)
```

## Unblocking Algorithm

When a job completes (status → 5, 6, 7, or 8), the background unblock task processes it:

```
For each completed job C:
  If C.status == COMPLETED:
    For each downstream job D that depends on C:
      If all of D's upstream dependencies are completed:
        D.status → READY
      Else:
        D remains BLOCKED

  If C.status IN (FAILED, CANCELED, TERMINATED):
    For each downstream job D:
      D.status → CANCELED  (cascade cancellation)
      Recursively cancel D's dependents

  C.unblocking_processed = 1
```

This runs in the `BackgroundUnblockTask` rather than inline in the HTTP handler, batching all
pending unblocks together for efficiency.

## Cycle Detection

Circular dependencies cause all jobs in the cycle to remain `BLOCKED` indefinitely — no job can
become `READY` because each is waiting for another in the cycle.

TorcPy does not currently detect cycles at creation time. If you suspect a cycle:

```bash
# Find jobs that are blocked but have all upstream jobs completed
sqlite3 torcpy.db "
SELECT j.id, j.name
FROM job j
WHERE j.workflow_id = 1
  AND j.status = 1  -- blocked
  AND NOT EXISTS (
    SELECT 1 FROM job_depends_on d
    JOIN job u ON d.upstream_job_id = u.id
    WHERE d.downstream_job_id = j.id
      AND u.status != 5
  );
"
```

Jobs returned by this query are blocked but have all dependencies satisfied — a sign of a data
inconsistency or a bug in the unblocking logic.

## Diamond Dependencies

Diamond patterns are handled correctly:

```
    A
   / \
  B   C
   \ /
    D
```

`D` depends on both `B` and `C`. The unblock task checks **all** upstream dependencies before
marking `D` as `READY`. D becomes ready only after both B and C complete.

```sql
-- D is ready when:
SELECT COUNT(*) = 0
FROM job_depends_on dep
JOIN job upstream ON dep.upstream_job_id = upstream.id
WHERE dep.downstream_job_id = D.id
  AND upstream.status != 5;
```

## Cascade Cancellation

When a job fails, all downstream dependents are canceled recursively:

```python
async def _cancel_downstream(db, job_id, workflow_id):
    # Find direct dependents
    rows = await db.fetchall(
        "SELECT downstream_job_id FROM job_depends_on WHERE upstream_job_id = ?",
        (job_id,),
    )
    for row in rows:
        downstream_id = row["downstream_job_id"]
        await db.execute(
            "UPDATE job SET status = 7 WHERE id = ? AND status IN (1, 2)",
            (downstream_id,),
        )
        # Recurse
        await _cancel_downstream(db, downstream_id, workflow_id)
```

Only `BLOCKED` (1) and `READY` (2) jobs are canceled — jobs already `RUNNING` (4) or `PENDING` (3)
are not canceled immediately (they will complete or fail on their own).
