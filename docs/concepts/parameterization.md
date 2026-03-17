# Parameter Expansion

TorcPy can expand a single job (or file) definition into many instances using the `parameters`
field. This is ideal for parameter sweeps, cross-validation, and multi-dataset pipelines.

## Syntax Overview

Add a `parameters` dict to any job or file spec:

```yaml
jobs:
  - name: train_{fold}
    command: python train.py --fold {fold}
    parameters:
      fold: "1:5"     # expands to fold=1, 2, 3, 4, 5
```

This creates **5 jobs**: `train_1`, `train_2`, `train_3`, `train_4`, `train_5`.

## Parameter Formats

### Integer Range

```yaml
parameters:
  i: "1:100"       # 1, 2, 3, ..., 100  (inclusive)
  i: "0:100:10"    # 0, 10, 20, ..., 100  (with step)
```

### Float Range

```yaml
parameters:
  lr: "0.0:1.0:0.1"   # 0.0, 0.1, 0.2, ..., 1.0
```

### List

```yaml
parameters:
  split: "[train, test, val]"
  batch: "[32, 64, 128]"
  lr: "[0.001, 0.01, 0.1]"
```

## Template Substitution

Use `{param_name}` or `{param_name:format}` in names, commands, paths, and dependency lists:

```yaml
- name: "job_{i:03d}"          # job_001, job_042, job_100
  command: "python run.py {i}"
  output_files: ["output_{i:03d}"]
```

### Format Specifiers

| Specifier | Example | Output |
|---|---|---|
| `{i}` | `i=5` | `5` |
| `{i:03d}` | `i=5` | `005` |
| `{i:05d}` | `i=42` | `00042` |
| `{lr:.4f}` | `lr=0.001` | `0.0010` |
| `{lr:.2e}` | `lr=0.001` | `1.00e-03` |
| `{name}` | `name=train` | `train` |

## Combining Parameters

### Cartesian Product (default)

All combinations of all parameters:

```yaml
jobs:
  - name: "train_{lr:.4f}_bs{batch}"
    command: "python train.py --lr {lr} --batch {batch}"
    parameters:
      lr: "[0.001, 0.01]"
      batch: "[32, 64]"
    parameter_mode: cartesian   # default
```

Produces **4 jobs**: `(0.001,32)`, `(0.001,64)`, `(0.01,32)`, `(0.01,64)`.

### Zip Mode

Pairs parameters positionally (like Python's `zip`):

```yaml
jobs:
  - name: "process_{dataset}_{model}"
    command: "python run.py --data {dataset} --model {model}"
    parameters:
      dataset: "[train, val, test]"
      model: "[small, medium, large]"
    parameter_mode: zip
```

Produces **3 jobs**: `(train,small)`, `(val,medium)`, `(test,large)`.

## Parameterized Files

Files can also be parameterized to match parameterized jobs:

```yaml
files:
  - name: "model_{lr:.4f}"
    path: "models/model_{lr:.4f}.pkl"
    parameters:
      lr: "[0.001, 0.01, 0.1]"

jobs:
  - name: "train_{lr:.4f}"
    command: "python train.py --lr {lr}"
    parameters:
      lr: "[0.001, 0.01, 0.1]"
    output_files: ["model_{lr:.4f}"]
```

## Regex Dependencies for Parameterized Jobs

Use `depends_on_regexes` to collect all parameterized jobs into a final step:

```yaml
jobs:
  - name: train_{fold}
    command: python train.py --fold {fold}
    parameters:
      fold: "1:10"

  - name: aggregate
    command: python aggregate.py
    depends_on_regexes:
      - "train_.*"    # waits for all 10 train jobs
```

## Full Example: Hyperparameter Sweep

```yaml title="sweep.yaml"
name: hyperparameter-sweep

files:
  - name: dataset
    path: data/train.csv
    st_mtime: 1710000000.0
  - name: checkpoint_{lr:.4f}_{bs}
    path: checkpoints/ckpt_{lr:.4f}_{bs}.pt
    parameters:
      lr: "[0.001, 0.01]"
      bs: "[32, 64]"

jobs:
  - name: train_{lr:.4f}_{bs}
    command: >
      python train.py
        --lr {lr}
        --batch {bs}
        --out checkpoints/ckpt_{lr:.4f}_{bs}.pt
    parameters:
      lr: "[0.001, 0.01]"
      bs: "[32, 64]"
    input_files: [dataset]
    output_files: [checkpoint_{lr:.4f}_{bs}]
    resource_requirements:
      num_cpus: 4
      memory: "8g"
      runtime: "PT1H"

  - name: select_best
    command: python select_best.py checkpoints/
    depends_on_regexes:
      - "train_.*"
```

Running this creates **4 training jobs** plus 1 final aggregation job.
