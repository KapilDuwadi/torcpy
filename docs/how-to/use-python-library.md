# How-To: Use the Python Library

TorcPy ships a fully-typed async Python client. Use it to build custom orchestration scripts,
integrate with notebooks, or embed TorcPy into larger applications.

## Basic Setup

```python
from torcpy.client import TorcClient

# Use as an async context manager (recommended)
async with TorcClient("http://localhost:8080/torcpy/v1") as client:
    wf = await client.get_workflow(1)
    print(wf.name)

# Or manage lifecycle manually
client = TorcClient()
await client.ping()
# ... do work ...
await client.close()
```

Set the server URL via environment variable to avoid hardcoding:

```bash
export TORCPY_API_URL=http://localhost:8080/torcpy/v1
```

```python
import os
from torcpy.client import TorcClient

url = os.environ.get("TORCPY_API_URL", "http://localhost:8080/torcpy/v1")
async with TorcClient(url) as client:
    ...
```

## Create and Run a Workflow from a Spec File

```python
import asyncio
from torcpy.client import TorcClient, WorkflowSpec, create_workflow_from_spec
from torcpy.client.job_runner import JobRunner, JobRunnerConfig

async def main():
    async with TorcClient() as client:
        # Load and create workflow
        spec = WorkflowSpec.from_file("pipeline.yaml")
        wf_id = await create_workflow_from_spec(client, spec)
        print(f"Created workflow {wf_id}")

        # Run locally
        config = JobRunnerConfig(
            poll_interval=2.0,
            output_dir="output/",
            max_parallel_jobs=0,   # 0 = unlimited (resource-constrained)
        )
        runner = JobRunner(client, wf_id, config)
        stats = await runner.run()
        print(f"Done: {stats}")

asyncio.run(main())
```

## Create a Workflow Programmatically

```python
from torcpy.client import TorcClient
from torcpy.models import (
    WorkflowCreate, JobCreate, FileCreate, ResourceRequirementsCreate
)
from torcpy.models.enums import JobStatus

async with TorcClient() as client:
    # 1. Create workflow
    wf = await client.create_workflow(
        WorkflowCreate(name="my-pipeline", user="alice")
    )
    wf_id = wf.id

    # 2. Create files
    f_in = await client.create_file(wf_id, FileCreate(
        workflow_id=wf_id, name="input", path="data/in.csv", st_mtime=1710000000.0
    ))
    f_out = await client.create_file(wf_id, FileCreate(
        workflow_id=wf_id, name="output", path="data/out.csv"
    ))

    # 3. Create resource requirements
    rr = await client.create_resource_requirements(wf_id, ResourceRequirementsCreate(
        workflow_id=wf_id, num_cpus=4, memory="8g", runtime="PT1H"
    ))

    # 4. Create jobs
    j1 = await client.create_job(wf_id, JobCreate(
        workflow_id=wf_id,
        name="process",
        command="python process.py",
        input_file_ids=[f_in.id],
        output_file_ids=[f_out.id],
        resource_requirements_id=rr.id,
    ))

    j2 = await client.create_job(wf_id, JobCreate(
        workflow_id=wf_id,
        name="report",
        command="python report.py",
        depends_on_job_ids=[j1.id],
    ))

    # 5. Initialize and run
    await client.initialize_workflow(wf_id)
```

## Claim and Execute Jobs Manually

For custom job runners:

```python
from torcpy.client import TorcClient
from torcpy.models.enums import JobStatus

async with TorcClient() as client:
    while True:
        jobs = await client.claim_next_jobs(workflow_id=1, count=5)
        if not jobs:
            await asyncio.sleep(2)
            continue

        for job in jobs:
            # Execute the job's command somehow
            result = run_subprocess(job.command)

            # Record result
            await client.create_result(1, ResultCreate(
                workflow_id=1,
                job_id=job.id,
                return_code=result.returncode,
                exec_time_minutes=result.duration / 60,
            ))

            # Complete it
            status = JobStatus.COMPLETED if result.returncode == 0 else JobStatus.FAILED
            await client.complete_job(1, job.id, status=status)
```

## Python API Reference

See the full [Python API Reference](../reference/python-api.md) for all available methods.
