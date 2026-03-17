# Workflow Reports

## Summary Report

Shows job counts grouped by status and total execution time:

```console
torcpy reports summary <workflow_id>
```

```
Workflow 42 Summary
  Total jobs: 101
  completed: 99
  failed: 2
  canceled: 0

  Total execution time: 312.4 minutes
  Failed results: 2
```

## Results Table

Shows per-job execution metrics:

```console
torcpy reports results <workflow_id>
```

```
 Results (workflow 42)
┏━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Job ID ┃ Return Code ┃ Time (min) ┃ Status    ┃ Peak Mem (MB) ┃
┡━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ 1      │ 0           │ 3.21       │ completed │ 512.4         │
│ 2      │ 0           │ 5.47       │ completed │ 1024.1        │
│ 47     │ 137         │ 12.00      │ failed    │               │
└────────┴─────────────┴────────────┴───────────┴───────────────┘
```

## JSON Output

All reports support `--format json` for scripting:

```console
torcpy reports results 42 --format json > results.json
python -c "
import json
data = json.load(open('results.json'))
failed = [r for r in data if r['return_code'] != 0]
print(f'Failed: {len(failed)}')
"
```

## Python Client

```python
from torcpy.client import TorcClient

async with TorcClient() as client:
    status = await client.workflow_status(workflow_id=42)
    results = await client.list_results(workflow_id=42)

    total_time = sum(
        r.get("exec_time_minutes", 0) or 0
        for r in results["items"]
    )
    print(f"Total CPU-minutes: {total_time:.1f}")
```
