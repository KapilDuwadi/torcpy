# Server Design

## Application Structure

```
src/torcpy/server/
├── app.py          # FastAPI app factory + lifespan
├── database.py     # SQLite connection, schema, helpers
├── background.py   # BackgroundUnblockTask
├── deps.py         # FastAPI dependency injection
└── api/
    ├── workflows.py
    ├── jobs.py
    ├── files.py
    ├── user_data.py
    ├── resource_requirements.py
    ├── results.py
    ├── compute_nodes.py
    ├── events.py
    ├── failure_handlers.py
    ├── schedulers.py
    └── health.py
```

## App Factory

`create_app(db_path)` builds the FastAPI application with lifespan:

```python
@asynccontextmanager
async def lifespan(app):
    db = Database(db_path)
    await db.connect()
    await db.init_schema()
    app.state.db = db

    bg_task = BackgroundUnblockTask(db, interval=1.0)
    bg_task.start()
    app.state.bg_unblock = bg_task
    yield

    await bg_task.stop()
    await db.close()
```

## Database Layer

`Database` wraps a single `aiosqlite.Connection`:

```python
# Regular transaction
async with db.transaction():
    await db.execute("INSERT ...")

# Write-locked transaction (job claiming)
async with db.write_transaction():
    rows = await db.fetchall("SELECT ...")
    await db.execute("UPDATE ...")
```

`db.fetchone()`, `db.fetchall()`, `db.insert()`, `db.executemany()` are convenience wrappers
over the raw aiosqlite connection.

## Dependency Injection

Every route handler receives the database via FastAPI's dependency injection:

```python
from torcpy.server.deps import get_db

@router.get("/{id}")
async def get_workflow(id: int, db: Database = Depends(get_db)):
    row = await db.fetchone("SELECT * FROM workflow WHERE id = ?", (id,))
    ...
```

`get_db` reads `request.app.state.db`, which was set during lifespan.

## Background Unblock Task

`BackgroundUnblockTask` runs as an `asyncio.Task` alongside the server:

```python
class BackgroundUnblockTask:
    async def _run(self):
        while self._running:
            await asyncio.wait_for(self._event.wait(), timeout=self.interval)
            self._event.clear()
            await self._process_pending_unblocks()

    async def _process_pending_unblocks(self):
        # Find jobs with status IN (5,6,7,8) AND unblocking_processed=0
        # For each: unblock dependents or cancel downstream
        # Set unblocking_processed=1
```

The task is woken via `bg_task.signal()` from `complete_job`, ensuring it runs promptly
after each completion rather than waiting for the full interval.

## JSON Serialization

Columns that store structured data (metadata, rules, slurm_config, etc.) are stored as JSON
strings in SQLite and deserialized on read:

```python
# Write
json.dumps(body.metadata) if body.metadata else None

# Read
json.loads(row["metadata"]) if row["metadata"] else None
```
