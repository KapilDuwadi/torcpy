"""Resource requirements models."""

import re

from pydantic import BaseModel, model_validator


def parse_memory_to_bytes(memory: str | None) -> int | None:
    """Parse memory string like '1g', '512m', '1024k' to bytes."""
    if memory is None:
        return None
    memory = memory.strip().lower()
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([kmgt]?)b?$", memory)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    multipliers = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
    return int(value * multipliers.get(unit, 1))


def parse_runtime_to_seconds(runtime: str | None) -> float | None:
    """Parse ISO8601 duration like 'PT30M', 'PT2H', 'P0DT1M' to seconds."""
    if runtime is None:
        return None
    runtime = runtime.strip().upper()
    match = re.match(
        r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$",
        runtime,
    )
    if not match:
        return None
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = float(match.group(4) or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


class ResourceRequirementsCreate(BaseModel):
    workflow_id: int
    num_cpus: int | None = None
    num_gpus: int | None = None
    num_nodes: int | None = None
    memory: str | None = None
    runtime: str | None = None

    memory_bytes: int | None = None
    runtime_s: float | None = None

    @model_validator(mode="after")
    def compute_derived(self) -> "ResourceRequirementsCreate":
        if self.memory and self.memory_bytes is None:
            self.memory_bytes = parse_memory_to_bytes(self.memory)
        if self.runtime and self.runtime_s is None:
            self.runtime_s = parse_runtime_to_seconds(self.runtime)
        return self


class ResourceRequirementsUpdate(BaseModel):
    num_cpus: int | None = None
    num_gpus: int | None = None
    num_nodes: int | None = None
    memory: str | None = None
    runtime: str | None = None


class ResourceRequirements(BaseModel):
    id: int
    workflow_id: int
    num_cpus: int | None = None
    num_gpus: int | None = None
    num_nodes: int | None = None
    memory: str | None = None
    runtime: str | None = None
    memory_bytes: int | None = None
    runtime_s: float | None = None
