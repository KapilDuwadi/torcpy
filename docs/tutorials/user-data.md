# Tutorial: Using User Data

**User data** items are named JSON values that jobs can read and write. Unlike files (which are
filesystem paths), user data is stored in TorcPy's database. Use it to pass structured
metrics, configuration, or small results between jobs.

## Goal

A tuning job finds optimal hyperparameters and stores them as user data. A training job reads
those parameters and runs final training.

## Workflow Spec

```yaml title="user_data_flow.yaml"
name: user-data-demo

user_data:
  - name: base_config
    data:
      epochs: 50
      early_stopping: true

  - name: best_params     # written by tune, read by train_final

jobs:
  - name: tune
    command: python tune.py --epochs 50
    input_user_data: [base_config]
    output_user_data: [best_params]

  - name: train_final
    command: python train.py
    input_user_data: [base_config, best_params]   # implicit dep on tune
    depends_on: [tune]    # explicit dep to be safe
```

## Ephemeral User Data

Mark user data as `is_ephemeral: true` to indicate it is only needed during the workflow run
and can be cleaned up after:

```yaml
user_data:
  - name: intermediate_embeddings
    is_ephemeral: true    # can be deleted after workflow completes
```

## Accessing User Data via the API

```python
from torcpy.client import TorcClient
from torcpy.models import UserDataCreate

async with TorcClient() as client:
    # Create
    ud = await client.create_user_data(
        workflow_id=1,
        body=UserDataCreate(
            workflow_id=1,
            name="best_params",
            data={"lr": 0.001, "batch": 64},
        ),
    )

    # List all user data
    result = await client.list_user_data(workflow_id=1)
    for item in result["items"]:
        print(item["name"], item["data"])
```

## Pattern: Passing Metrics Between Stages

```yaml title="metrics_flow.yaml"
name: metrics-pipeline

user_data:
  - name: val_metrics      # written by validate
  - name: test_metrics     # written by test

jobs:
  - name: train
    command: python train.py
    output_user_data: [val_metrics]

  - name: validate
    command: python validate.py
    input_user_data: [val_metrics]   # implicit dep on train
    output_user_data: [test_metrics]

  - name: report
    command: python report.py
    input_user_data: [val_metrics, test_metrics]
```

## Next Steps

- [Concepts: Dependency Resolution](../concepts/dependencies.md)
- [Reference: Workflow Spec](../reference/workflow-spec.md)
