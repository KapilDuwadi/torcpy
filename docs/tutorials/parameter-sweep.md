# Tutorial: Parameter Sweeps

Parameter sweeps explore multiple configurations simultaneously. TorcPy's Cartesian expansion
makes it easy to search over grids of hyperparameters.

## Goal

Train models across a grid of learning rates and batch sizes, then select the best.

## 2D Cartesian Sweep

```yaml title="sweep.yaml"
name: hyperparameter-sweep
project: nlp-experiment

files:
  - name: dataset
    path: data/train.csv
    st_mtime: 1710000000.0

  - name: checkpoint_{lr:.4f}_{bs}
    path: checkpoints/lr{lr:.4f}_bs{bs}.pt
    parameters:
      lr: "[0.0001, 0.001, 0.01]"
      bs: "[32, 64, 128]"

jobs:
  - name: train_{lr:.4f}_{bs}
    command: >
      python train.py
        --lr {lr}
        --batch-size {bs}
        --output checkpoints/lr{lr:.4f}_bs{bs}.pt
    parameters:
      lr: "[0.0001, 0.001, 0.01]"
      bs: "[32, 64, 128]"
    parameter_mode: cartesian   # 3 × 3 = 9 jobs
    input_files: [dataset]
    output_files: [checkpoint_{lr:.4f}_{bs}]
    resource_requirements:
      num_cpus: 4
      num_gpus: 1
      memory: "8g"
      runtime: "PT2H"
    priority: 10

  - name: select_best
    command: python select_best.py checkpoints/
    depends_on_regexes:
      - "train_.*"

  - name: evaluate_best
    command: python evaluate.py
    depends_on: [select_best]
```

This creates **9 training jobs** (3 lr × 3 bs) + 1 selection + 1 evaluation.

## Run It

```console
torcpy run sweep.yaml
```

```
Created workflow 1
Initialized: 9 ready, 2 blocked
Running 9 training jobs in parallel...

Workflow 1 finished:
  Completed: 11
  Failed:    0
```

## Zip Mode: Paired Parameters

When parameters should be paired (not crossed), use `parameter_mode: zip`:

```yaml
jobs:
  - name: experiment_{name}
    command: python run.py --config configs/{name}.json --seed {seed}
    parameters:
      name: "[small, medium, large]"
      seed: "[42, 123, 999]"
    parameter_mode: zip   # (small,42), (medium,123), (large,999)
```

## Multi-Stage Sweep: Train → Finetune

```yaml title="two_stage_sweep.yaml"
name: two-stage-sweep

files:
  - name: pretrained_{lr:.4f}
    path: models/pretrained_{lr:.4f}.pt
    parameters:
      lr: "[0.001, 0.01]"
  - name: finetuned_{lr:.4f}_{ft_lr:.5f}
    path: models/fine_{lr:.4f}_{ft_lr:.5f}.pt
    parameters:
      lr: "[0.001, 0.01]"
      ft_lr: "[0.0001, 0.00001]"

jobs:
  - name: pretrain_{lr:.4f}
    command: python pretrain.py --lr {lr} --out models/pretrained_{lr:.4f}.pt
    parameters:
      lr: "[0.001, 0.01]"
    output_files: [pretrained_{lr:.4f}]

  - name: finetune_{lr:.4f}_{ft_lr:.5f}
    command: >
      python finetune.py
        --base models/pretrained_{lr:.4f}.pt
        --lr {ft_lr}
        --out models/fine_{lr:.4f}_{ft_lr:.5f}.pt
    parameters:
      lr: "[0.001, 0.01]"
      ft_lr: "[0.0001, 0.00001]"
    input_files: [pretrained_{lr:.4f}]   # implicit dep on pretrain_{lr:.4f}
    output_files: [finetuned_{lr:.4f}_{ft_lr:.5f}]
```

This creates 2 pretrain jobs and 4 finetune jobs (2 lr × 2 ft_lr), with correct
implicit dependencies between matching `lr` values.

## Next Steps

- [Parameter Syntax Reference](../reference/parameterization.md)
- [Multi-Stage Pipeline](./multi-stage.md)
