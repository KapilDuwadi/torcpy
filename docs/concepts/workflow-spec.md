# Workflow Specification

TorcPy workflows are defined in **YAML** or **JSON** files. The spec describes the workflow
metadata, files, user data, jobs, schedulers, and failure handlers.

## File Formats

| Extension | Format | Notes |
|---|---|---|
| `.yaml`, `.yml` | YAML | Recommended for readability |
| `.json` | JSON | Strict JSON |
| `.json5` | JSON5 | JSON with comments (requires `json5` package) |

## Top-Level Structure

```yaml
name: my-workflow          # required
user: alice                # optional, defaults to $USER
project: ml-project        # optional grouping label
metadata:                  # optional arbitrary JSON
  version: "1.0"

files:        []           # file artifacts
user_data:    []           # key-value data
jobs:         []           # computational tasks
schedulers:   []           # execution environments
failure_handlers: []       # retry/recovery rules
```

## `files`

Files represent input/output artifacts. They create implicit dependencies between jobs.

```yaml
files:
  - name: input             # required, unique name
    path: data/input.csv    # filesystem path (optional)
    st_mtime: 1710000000.0  # set for pre-existing inputs; omit for outputs
```

## `user_data`

Named data items (JSON values) that can be passed between jobs.

```yaml
user_data:
  - name: hyperparams
    data:
      learning_rate: 0.001
      batch_size: 64
    is_ephemeral: false     # true = deleted after workflow completes
```

## `jobs`

The core of the workflow — each job is a unit of computation.

```yaml
jobs:
  - name: train             # required, unique name
    command: python train.py --lr 0.001

    # Dependencies
    depends_on: [preprocess]          # explicit job names
    depends_on_regexes: ["train_.*"]  # regex patterns

    # File relationships
    input_files: [features]
    output_files: [model]

    # Data relationships
    input_user_data: [hyperparams]
    output_user_data: [metrics]

    # Execution
    priority: 10                     # higher = scheduled first (default 0)
    cancel_on_blocking_job_failure: false
    supports_termination: false      # true = handle SIGTERM gracefully

    # Resources
    resource_requirements:
      num_cpus: 4
      num_gpus: 1
      num_nodes: 1
      memory: "8g"         # 1k, 512m, 2g, 1t
      runtime: "PT2H"      # ISO 8601 duration

    # Failure handling
    failure_handler: retry_on_oom

    # Parameterization
    parameters:
      fold: "1:5"
      lr: "[0.001, 0.01, 0.1]"
    parameter_mode: cartesian   # or "zip"
```

## `schedulers`

=== "Local"

    ```yaml
    schedulers:
      - type: local
        num_cpus: 8
        memory: "32g"
    ```

=== "Slurm"

    ```yaml
    schedulers:
      - type: slurm
        account: myproject
        partition: gpu
        slurm_config:
          gres: gpu:1
          time: "02:00:00"
    ```

## `failure_handlers`

Define retry rules triggered by specific exit codes:

```yaml
failure_handlers:
  - name: retry_on_oom
    rules:
      - exit_codes: [137, 139]       # OOM kill / segfault
        max_retries: 2
        recovery_command: echo "Retrying after OOM"
      - exit_code_ranges: [[1, 10]]  # any exit 1–10
        max_retries: 1
    default_max_retries: 0
```

## Complete Example

```yaml title="full_example.yaml"
name: hyperparameter-sweep
user: alice
project: nlp-research

files:
  - name: corpus
    path: data/corpus.txt
    st_mtime: 1710000000.0
  - name: model_{lr:.4f}
    path: models/model_{lr:.4f}.pkl
    parameters:
      lr: "[0.001, 0.01, 0.1]"

user_data:
  - name: best_lr
  - name: training_config
    data: {epochs: 10, seed: 42}

failure_handlers:
  - name: retry_oom
    rules:
      - exit_codes: [137]
        max_retries: 2

jobs:
  - name: train_{lr:.4f}
    command: python train.py --lr {lr:.4f} --output models/model_{lr:.4f}.pkl
    parameters:
      lr: "[0.001, 0.01, 0.1]"
    input_files: [corpus]
    output_files: [model_{lr:.4f}]
    input_user_data: [training_config]
    resource_requirements:
      num_cpus: 4
      memory: "8g"
      runtime: "PT1H"
    failure_handler: retry_oom
    priority: 10

  - name: select_best
    command: python select_best.py
    depends_on_regexes: ["train_.*"]
    output_user_data: [best_lr]

  - name: final_report
    command: python report.py
    depends_on: [select_best]
    input_user_data: [best_lr]
```
