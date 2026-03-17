# Resource Management

TorcPy tracks CPU, memory, and GPU resources on each worker node. Jobs only run when sufficient
resources are available.

## Resource Requirements Spec

Define per-job resource requirements inline:

```yaml
jobs:
  - name: heavy_job
    command: python compute.py
    resource_requirements:
      num_cpus: 8         # number of CPU cores
      num_gpus: 2         # number of GPU devices
      num_nodes: 1        # number of compute nodes
      memory: "32g"       # memory requirement
      runtime: "PT4H"     # maximum walltime (ISO 8601)
```

## Memory Format

Memory is specified as a string with a unit suffix:

| Value | Bytes |
|---|---|
| `"512k"` | 524,288 |
| `"1m"` | 1,048,576 |
| `"4g"` | 4,294,967,296 |
| `"1t"` | 1,099,511,627,776 |

Case-insensitive. The `b` suffix is optional (`"4gb"` = `"4g"`).

## Runtime Format

Runtime uses ISO 8601 duration format:

| Value | Duration |
|---|---|
| `"PT30M"` | 30 minutes |
| `"PT2H"` | 2 hours |
| `"PT1H30M"` | 1 hour 30 minutes |
| `"P1D"` | 1 day |
| `"PT90S"` | 90 seconds |

## Resource Auto-Detection

Workers automatically detect available resources on startup:

```python
from torcpy.client.resource_tracker import ResourceTracker

tracker = ResourceTracker.detect_local()
print(f"CPUs: {tracker.total_cpus}")
print(f"Memory: {tracker.total_memory_bytes / 1e9:.1f} GB")
print(f"GPUs: {tracker.total_gpus}")
```

GPU detection uses `CUDA_VISIBLE_DEVICES` if set, otherwise queries `nvidia-smi`.

## Scheduling Behaviour

The job runner only claims a new job if it fits within available resources:

```
available_cpus  >= job.num_cpus
available_mem   >= job.memory_bytes
available_gpus  >= job.num_gpus
```

If a job doesn't fit, it is returned to `ready` status and will be claimed later.

## Claim Sort Order

Control how the server prioritises ready jobs when multiple workers compete:

| Sort Method | Behaviour |
|---|---|
| `priority` (default) | Higher `priority` value scheduled first |
| `gpus_runtime_memory` | Most GPU-hungry jobs first |
| `cpus_runtime_memory` | Most CPU-hungry jobs first |

Set in the Python client:

```python
from torcpy.models.enums import ClaimJobsSortMethod

jobs = await client.claim_next_jobs(
    workflow_id=1,
    count=5,
    sort=ClaimJobsSortMethod.GPUS_RUNTIME_MEMORY,
)
```

## Job Priority

Set `priority` on individual jobs to influence scheduling order (higher = sooner):

```yaml
jobs:
  - name: critical_step
    command: python critical.py
    priority: 100     # runs before lower-priority jobs

  - name: background_step
    command: python bg.py
    priority: 0       # default
```
