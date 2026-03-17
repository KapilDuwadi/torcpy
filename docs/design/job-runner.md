# Job Runner Design

## Overview

The `JobRunner` is the local execution engine for TorcPy workflows. It sits between the server
(which owns job state) and the operating system (where jobs actually execute as subprocesses).

```
┌─────────────────────────────────────────────────────┐
│                     JobRunner                       │
│                                                     │
│  ┌──────────────┐    ┌────────────┐                 │
│  │ claim_next   │───►│ can_fit?   │                 │
│  │ jobs (poll)  │    │ (resources)│                 │
│  └──────────────┘    └─────┬──────┘                 │
│                            │ yes                    │
│                     ┌──────▼──────┐                 │
│                     │  allocate   │                 │
│                     │  resources  │                 │
│                     └──────┬──────┘                 │
│                            │                        │
│                     ┌──────▼──────┐                 │
│                     │ asyncio     │                 │
│                     │ .create_    │                 │
│                     │  task()     │                 │
│                     └──────┬──────┘                 │
│                            │ on completion          │
│                     ┌──────▼──────┐                 │
│                     │ complete_   │                 │
│                     │ job (API)   │                 │
│                     └──────┬──────┘                 │
│                            │                        │
│                     ┌──────▼──────┐                 │
│                     │  release    │                 │
│                     │  resources  │                 │
│                     └─────────────┘                 │
└─────────────────────────────────────────────────────┘
```

## Configuration

```python
@dataclass
class JobRunnerConfig:
    workflow_id: int
    output_dir: Path = Path("output")
    stdio_mode: StdioMode = StdioMode.SEPARATE
    poll_interval: float = 2.0          # seconds between server polls
    max_concurrent_jobs: int | None = None  # None = unlimited (resource-limited only)
    claim_batch_size: int = 10          # jobs requested per claim call
```

## Execution Loop Detail

```python
async def run(self) -> None:
    await self._setup_output_dir()
    self._install_signal_handlers()

    while not self._shutdown:
        # 1. Calculate how many more jobs we can accept
        slots = self._available_slots()
        if slots > 0:
            jobs = await self.client.claim_next_jobs(
                self.config.workflow_id,
                n=min(slots, self.config.claim_batch_size),
            )
            for job in jobs:
                self._launch(job)

        # 2. Check for workflow terminal state
        if await self._workflow_is_done():
            break

        # 3. Wait for tasks to complete or poll interval to elapse
        if self._active_tasks:
            done, _ = await asyncio.wait(
                self._active_tasks,
                timeout=self.config.poll_interval,
                return_when=asyncio.FIRST_COMPLETED,
            )
            await self._handle_completed(done)
        else:
            await asyncio.sleep(self.config.poll_interval)

    # 4. Drain remaining tasks
    if self._active_tasks:
        done, _ = await asyncio.wait(self._active_tasks)
        await self._handle_completed(done)
```

## Job Lifecycle (Single Job)

```
claim_next_jobs → job enters PENDING state on server
       │
       ▼
asyncio.create_task(_run_single_job(job))
       │
       ▼
run_command(job.command, stdout_path, stderr_path, walltime_seconds)
       │
       ├── success → exit_code=0
       │       └── complete_job(status=COMPLETED, result=...)
       │
       ├── nonzero exit → exit_code≠0
       │       └── complete_job(status=FAILED, result=...)
       │
       └── walltime exceeded → asyncio.TimeoutError
               └── complete_job(status=TERMINATED, result=...)
```

## Resource Slot Calculation

```python
def _available_slots(self) -> int:
    resource_limited = self.resource_tracker.free_slots()
    if self.config.max_concurrent_jobs is not None:
        concurrency_limited = self.config.max_concurrent_jobs - len(self._active_tasks)
        return min(resource_limited, concurrency_limited)
    return resource_limited
```

`ResourceTracker.free_slots()` returns the number of additional jobs that could be accommodated
given current free CPUs, memory, and GPUs. A job requiring 4 CPUs on a 16-CPU machine with 3 jobs
already running (using 12 CPUs) yields 1 free slot.

## Result Reporting

When a job finishes, the runner sends a `CompleteJob` payload:

```python
@dataclass
class JobResult:
    status: JobStatus          # COMPLETED / FAILED / TERMINATED
    exit_code: int | None
    stdout_path: str | None
    stderr_path: str | None
    start_time: float          # Unix timestamp
    end_time: float
    wall_time_seconds: float
    cpu_time_seconds: float | None
    max_memory_bytes: int | None
```

Resource metrics (CPU time, peak memory) are collected by reading `/proc/{pid}/stat` on Linux or
via `psutil` cross-platform.

## Signal Handling

```python
def _install_signal_handlers(self) -> None:
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, self._handle_shutdown_signal)

def _handle_shutdown_signal(self) -> None:
    self._shutdown = True
    # Active tasks are allowed to finish naturally
    # No new jobs will be claimed
```

On `Ctrl-C`, the runner stops claiming jobs but waits for all running jobs to finish before
exiting. This prevents jobs from being left in `PENDING` state without a runner to complete them.

## Output Directory Layout

```
output/
  job_1.stdout      # stdio_mode=separate (default)
  job_1.stderr
  job_2.stdout
  job_2.stderr
  job_3.log         # stdio_mode=combined
  job_4.stderr      # stdio_mode=no_stdout
```

The output directory is created on `runner.run()` if it does not exist.

## Walltime Enforcement

```python
async def _run_with_walltime(
    self,
    command: str,
    walltime: float | None,
    **kwargs,
) -> int:
    if walltime is None:
        return await run_command(command, **kwargs)
    try:
        return await asyncio.wait_for(run_command(command, **kwargs), timeout=walltime)
    except asyncio.TimeoutError:
        # Process group kill happens inside run_command's finally block
        raise
```

The walltime comes from `job.resource_requirements.runtime_limit_seconds`. Jobs without a runtime
limit run until they exit naturally.
