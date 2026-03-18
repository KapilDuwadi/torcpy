"""Resource tracking for the job runner.

Tracks available CPU, memory, and GPU resources on the local machine
and determines whether a job can fit within current availability.
"""

from __future__ import annotations

import logging
import os
import platform
from dataclasses import dataclass, field

from torcpy.models.resource_requirements import ResourceRequirements

logger = logging.getLogger(__name__)


@dataclass
class ResourceAllocation:
    """Resources allocated to a single running job."""

    job_id: int
    cpus: int = 0
    memory_bytes: int = 0
    gpus: int = 0


@dataclass
class ResourceTracker:
    """Tracks available compute resources."""

    total_cpus: int = 0
    total_memory_bytes: int = 0
    total_gpus: int = 0
    allocations: dict[int, ResourceAllocation] = field(default_factory=dict)

    @classmethod
    def detect_local(cls) -> ResourceTracker:
        """Auto-detect local machine resources."""
        cpus = os.cpu_count() or 1

        # Detect memory
        memory_bytes = 0
        try:
            if platform.system() == "Linux":
                with open("/proc/meminfo") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            kb = int(line.split()[1])
                            memory_bytes = kb * 1024
                            break
            elif platform.system() == "Darwin":
                import subprocess

                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True,
                    text=True,
                )
                memory_bytes = int(result.stdout.strip())
            elif platform.system() == "Windows":
                import subprocess

                result = subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
                    ],
                    capture_output=True,
                    text=True,
                )
                memory_bytes = int(result.stdout.strip())
        except Exception:
            memory_bytes = 8 * 1024**3  # default 8GB

        # Detect GPUs
        gpus = 0
        cuda_devices = os.environ.get("CUDA_VISIBLE_DEVICES")
        if cuda_devices:
            gpus = len([d for d in cuda_devices.split(",") if d.strip()])
        else:
            try:
                import subprocess

                result = subprocess.run(
                    ["nvidia-smi", "-L"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    gpus = len(result.stdout.strip().split("\n"))
            except FileNotFoundError:
                pass

        tracker = cls(
            total_cpus=cpus,
            total_memory_bytes=memory_bytes,
            total_gpus=gpus,
        )
        logger.info(
            "Detected resources: %d CPUs, %.1f GB memory, %d GPUs",
            cpus,
            memory_bytes / 1024**3,
            gpus,
        )
        return tracker

    @property
    def used_cpus(self) -> int:
        return sum(a.cpus for a in self.allocations.values())

    @property
    def used_memory_bytes(self) -> int:
        return sum(a.memory_bytes for a in self.allocations.values())

    @property
    def used_gpus(self) -> int:
        return sum(a.gpus for a in self.allocations.values())

    @property
    def available_cpus(self) -> int:
        return self.total_cpus - self.used_cpus

    @property
    def available_memory_bytes(self) -> int:
        return self.total_memory_bytes - self.used_memory_bytes

    @property
    def available_gpus(self) -> int:
        return self.total_gpus - self.used_gpus

    def can_fit(self, rr: ResourceRequirements | None) -> bool:
        """Check if the resource requirements fit within available resources."""
        if rr is None:
            return True

        cpus_needed = rr.num_cpus or 0
        mem_needed = rr.memory_bytes or 0
        gpus_needed = rr.num_gpus or 0

        return (
            cpus_needed <= self.available_cpus
            and mem_needed <= self.available_memory_bytes
            and gpus_needed <= self.available_gpus
        )

    def allocate(self, job_id: int, rr: ResourceRequirements | None) -> None:
        """Allocate resources for a job."""
        alloc = ResourceAllocation(
            job_id=job_id,
            cpus=rr.num_cpus or 0 if rr else 0,
            memory_bytes=rr.memory_bytes or 0 if rr else 0,
            gpus=rr.num_gpus or 0 if rr else 0,
        )
        self.allocations[job_id] = alloc
        logger.debug(
            "Allocated resources for job %d: %d CPUs, %d bytes mem, %d GPUs",
            job_id,
            alloc.cpus,
            alloc.memory_bytes,
            alloc.gpus,
        )

    def release(self, job_id: int) -> None:
        """Release resources for a completed job."""
        if job_id in self.allocations:
            del self.allocations[job_id]
            logger.debug("Released resources for job %d", job_id)
