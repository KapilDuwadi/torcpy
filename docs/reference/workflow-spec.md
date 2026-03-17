# Workflow Specification Reference

Complete reference for all fields in the workflow spec format.

## Top-Level Fields

| Field | Type | Required | Description |
|---|---|:---:|---|
| `name` | string | ✓ | Workflow name |
| `user` | string | | Owner username (defaults to `$USER`) |
| `project` | string | | Project/group label for organization |
| `metadata` | object | | Arbitrary JSON metadata |
| `slurm_defaults` | object | | Default Slurm parameters |
| `execution_config` | object | | Execution mode configuration |
| `files` | list[FileSpec] | | File artifact definitions |
| `user_data` | list[UserDataSpec] | | Named data items |
| `jobs` | list[JobSpec] | | Job definitions |
| `schedulers` | list[SchedulerSpec] | | Scheduler configurations |
| `failure_handlers` | list[FailureHandlerSpec] | | Retry rules |

---

## FileSpec

| Field | Type | Required | Description |
|---|---|:---:|---|
| `name` | string | ✓ | Unique name (supports `{param}` templates) |
| `path` | string | | Filesystem path |
| `st_mtime` | float | | Unix timestamp — marks as pre-existing input |
| `parameters` | object | | Parameter expansion spec |

---

## UserDataSpec

| Field | Type | Required | Description |
|---|---|:---:|---|
| `name` | string | ✓ | Unique name |
| `data` | any | | Initial JSON value |
| `is_ephemeral` | bool | | If true, can be deleted after completion |
| `parameters` | object | | Parameter expansion spec |

---

## JobSpec

| Field | Type | Required | Description |
|---|---|:---:|---|
| `name` | string | ✓ | Unique name (supports templates) |
| `command` | string | | Shell command to execute |
| `depends_on` | list[string] | | Explicit dependency job names |
| `depends_on_regexes` | list[string] | | Regex patterns for dependency matching |
| `input_files` | list[string] | | File names this job reads |
| `output_files` | list[string] | | File names this job writes |
| `input_user_data` | list[string] | | User data names this job reads |
| `output_user_data` | list[string] | | User data names this job writes |
| `resource_requirements` | ResourceRequirementsSpec | | CPU/memory/GPU/runtime |
| `failure_handler` | string | | Name of a `FailureHandlerSpec` |
| `priority` | int | | Scheduling priority (higher = earlier, default 0) |
| `cancel_on_blocking_job_failure` | bool | | Cancel this job if a dep fails (default false) |
| `supports_termination` | bool | | Handles SIGTERM gracefully (default false) |
| `parameters` | object | | Parameter expansion spec |
| `parameter_mode` | `"cartesian"` \| `"zip"` | | Expansion mode (default `"cartesian"`) |

---

## ResourceRequirementsSpec

| Field | Type | Description |
|---|---|---|
| `num_cpus` | int | Number of CPU cores |
| `num_gpus` | int | Number of GPU devices |
| `num_nodes` | int | Number of compute nodes |
| `memory` | string | Memory string (`"1g"`, `"512m"`, etc.) |
| `runtime` | string | ISO 8601 duration (`"PT2H"`, `"PT30M"`) |

---

## SchedulerSpec

=== "Local"

    | Field | Type | Description |
    |---|---|---|
    | `type` | `"local"` | Scheduler type |
    | `num_cpus` | int | Available CPU cores |
    | `memory` | string | Available memory |

=== "Slurm"

    | Field | Type | Description |
    |---|---|---|
    | `type` | `"slurm"` | Scheduler type |
    | `account` | string | Slurm account name |
    | `partition` | string | Slurm partition |
    | `slurm_config` | object | Additional Slurm parameters |

---

## FailureHandlerSpec

| Field | Type | Description |
|---|---|---|
| `name` | string | Unique handler name (referenced by jobs) |
| `rules` | list[FailureHandlerRuleSpec] | Per-exit-code rules |
| `default_max_retries` | int | Default retry count if no rule matches |
| `default_recovery_command` | string | Command to run before retry |

### FailureHandlerRuleSpec

| Field | Type | Description |
|---|---|---|
| `exit_codes` | list[int] | Exact exit codes this rule matches |
| `exit_code_ranges` | list[[int,int]] | Exit code ranges `[[1,10], [20,30]]` |
| `max_retries` | int | Maximum number of retries |
| `recovery_command` | string | Command to run before retrying |
