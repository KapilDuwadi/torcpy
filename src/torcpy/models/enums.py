"""Enumerations for TorcPy models."""

from enum import IntEnum, StrEnum


class JobStatus(IntEnum):
    """Job status values stored as integers in the database."""

    UNINITIALIZED = 0
    BLOCKED = 1
    READY = 2
    PENDING = 3
    RUNNING = 4
    COMPLETED = 5
    FAILED = 6
    CANCELED = 7
    TERMINATED = 8
    DISABLED = 9
    PENDING_FAILED = 10

    def is_terminal(self) -> bool:
        return self in (
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELED,
            JobStatus.TERMINATED,
            JobStatus.DISABLED,
        )

    def is_active(self) -> bool:
        return self in (JobStatus.PENDING, JobStatus.RUNNING)


class EventSeverity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class StdioMode(StrEnum):
    SEPARATE = "separate"
    COMBINED = "combined"
    NO_STDOUT = "no_stdout"
    NO_STDERR = "no_stderr"
    NONE = "none"


class TriggerType(StrEnum):
    ON_WORKFLOW_START = "on_workflow_start"
    ON_WORKFLOW_COMPLETE = "on_workflow_complete"
    ON_JOBS_READY = "on_jobs_ready"
    ON_JOBS_COMPLETE = "on_jobs_complete"


class ActionType(StrEnum):
    RUN_COMMANDS = "run_commands"
    SCHEDULE_NODES = "schedule_nodes"


class ClaimJobsSortMethod(StrEnum):
    GPUS_RUNTIME_MEMORY = "gpus_runtime_memory"
    CPUS_RUNTIME_MEMORY = "cpus_runtime_memory"
    PRIORITY = "priority"
