# How-To: Set Resource Requirements

Resource requirements tell TorcPy how much CPU, memory, and GPU a job needs. Workers only
claim jobs that fit within available resources.

## In the Workflow Spec

```yaml
jobs:
  - name: gpu_train
    command: python train.py
    resource_requirements:
      num_cpus: 8       # number of CPU cores
      num_gpus: 1       # number of GPU devices
      num_nodes: 1      # number of compute nodes
      memory: "32g"     # memory in k/m/g/t
      runtime: "PT4H"   # max walltime (ISO 8601)
```

## Memory Formats

| Value | Amount |
|---|---|
| `"512k"` | 512 KiB |
| `"1m"` | 1 MiB |
| `"8g"` | 8 GiB |
| `"2t"` | 2 TiB |

## Runtime Formats (ISO 8601)

| Value | Duration |
|---|---|
| `"PT30M"` | 30 minutes |
| `"PT2H"` | 2 hours |
| `"PT1H30M"` | 1 hour 30 minutes |
| `"P1D"` | 1 day |

## Omitting Resource Requirements

Jobs with no `resource_requirements` are always considered to fit and will be claimed
immediately (no resource checking). This is fine for lightweight jobs like shell commands.

## Via the Python Client

```python
from torcpy.client import TorcClient
from torcpy.models import ResourceRequirementsCreate

async with TorcClient() as client:
    rr = await client.create_resource_requirements(
        workflow_id=1,
        body=ResourceRequirementsCreate(
            workflow_id=1,
            num_cpus=4,
            memory="16g",
            runtime="PT2H",
        ),
    )
    # Use rr.id in JobCreate(resource_requirements_id=rr.id, ...)
```

## Checking What Workers Detect

```python
from torcpy.client.resource_tracker import ResourceTracker

tracker = ResourceTracker.detect_local()
print(f"CPUs available: {tracker.total_cpus}")
print(f"Memory available: {tracker.total_memory_bytes / 1e9:.1f} GB")
print(f"GPUs available: {tracker.total_gpus}")
```
