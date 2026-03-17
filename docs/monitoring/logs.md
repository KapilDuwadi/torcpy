# Job Logs

TorcPy captures stdout and stderr for each job as files on the worker's filesystem.

## Default Log Location

By default, logs are written to the `output/` directory in the current working directory:

```
output/
  job_1.stdout
  job_1.stderr
  job_2.stdout
  job_2.stderr
  ...
```

## Custom Output Directory

```console
torcpy workflows run 42 --output-dir /scratch/my_logs
torcpy run pipeline.yaml --output-dir /scratch/my_logs
```

## Log File Naming

Files are named `job_{id}.stdout` and `job_{id}.stderr`. Get the job ID from:

```console
torcpy jobs list 42
```

## Stdio Modes

Control what is captured by setting `stdio_mode` in the runner config:

| Mode | Files created |
|---|---|
| `separate` (default) | `job_N.stdout` + `job_N.stderr` |
| `combined` | `job_N.log` (stdout + stderr merged) |
| `no_stdout` | `job_N.stderr` only |
| `no_stderr` | `job_N.stdout` only |
| `none` | No files — output discarded |

In Python:

```python
from torcpy.client.job_runner import JobRunnerConfig
from torcpy.models.enums import StdioMode

config = JobRunnerConfig(
    output_dir="/scratch/logs",
    stdio_mode=StdioMode.COMBINED,
)
```

## Viewing Logs

```bash
# View stderr for job 47
cat output/job_47.stderr

# Follow stdout in real time (if job is running)
tail -f output/job_47.stdout

# Search across all logs
grep -r "Error" output/
grep -r "OOMKill" output/
```
