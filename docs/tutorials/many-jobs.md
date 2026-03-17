# Tutorial: Many Independent Jobs

When you have hundreds or thousands of independent jobs (e.g., processing many files, running
simulations), TorcPy's parameter expansion makes it trivial to define them all from one spec.

## Goal

Run 100 independent simulation jobs in parallel, then aggregate results.

## Workflow Spec

```yaml title="hundred_jobs.yaml"
name: simulation-sweep

files:
  - name: sim_config
    path: config/sim.json
    st_mtime: 1710000000.0

  - name: result_{i:03d}
    path: results/sim_{i:03d}.json
    parameters:
      i: "1:100"

jobs:
  - name: simulate_{i:03d}
    command: python simulate.py --seed {i} --output results/sim_{i:03d}.json
    parameters:
      i: "1:100"
    input_files: [sim_config]
    output_files: [result_{i:03d}]
    resource_requirements:
      num_cpus: 2
      memory: "2g"
      runtime: "PT30M"

  - name: aggregate
    command: python aggregate.py --input-dir results/ --output summary.json
    depends_on_regexes:
      - "simulate_.*"
```

This single spec creates **100 simulation jobs** + 1 aggregation job.

## Run It

```console
torcpy run hundred_jobs.yaml
```

TorcPy will run as many jobs in parallel as your resources allow:

```
Created workflow 1
Initialized: 100 ready, 1 blocked
Running job 1:   simulate_001
Running job 2:   simulate_002
Running job 3:   simulate_003
...
Running job 101: aggregate

Workflow 1 finished:
  Completed: 101
  Failed:    0
```

## Controlling Parallelism

The job runner uses resource tracking to limit parallelism automatically. With
`num_cpus: 2` per job on a 16-core machine, at most 8 jobs run simultaneously.

You can also set `max_parallel_jobs` in the runner config:

```python
from torcpy.client.job_runner import JobRunnerConfig

config = JobRunnerConfig(
    max_parallel_jobs=10,    # hard cap regardless of resources
    poll_interval=1.0,
    output_dir="output/",
)
```

## Checking Progress

While the workflow runs:

```console
torcpy workflows status 1
```

```
Workflow 1
  Total jobs: 101
  Job status:
    completed: 47
    running: 8
    pending: 3
    ready: 42
    blocked: 1
```

## Next Steps

- [Parameter Sweeps](./parameter-sweep.md) — Multi-dimensional parameter expansion
- [How-To: Track Workflow Status](../how-to/track-status.md)
