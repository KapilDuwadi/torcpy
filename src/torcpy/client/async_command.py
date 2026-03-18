"""Async subprocess execution wrapper.

Provides non-blocking job execution with stdout/stderr capture,
walltime enforcement, and signal handling.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from torcpy.models.enums import StdioMode

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of an executed command."""

    return_code: int
    exec_time_seconds: float
    stdout_path: str | None = None
    stderr_path: str | None = None


async def run_command(
    command: str,
    *,
    job_id: int = 0,
    work_dir: str | None = None,
    env: dict[str, str] | None = None,
    stdio_mode: StdioMode = StdioMode.SEPARATE,
    output_dir: str | None = None,
    walltime_seconds: float | None = None,
) -> CommandResult:
    """Execute a shell command asynchronously.

    Args:
        command: Shell command string to execute
        job_id: Job ID for naming output files
        work_dir: Working directory for the process
        env: Additional environment variables
        stdio_mode: How to capture stdout/stderr
        output_dir: Directory for stdout/stderr files
        walltime_seconds: Maximum execution time in seconds

    Returns:
        CommandResult with return code and timing
    """
    out_dir = Path(output_dir or ".")
    out_dir.mkdir(parents=True, exist_ok=True)

    stdout_path: str | None = None
    stderr_path: str | None = None

    process_env = os.environ.copy()
    if env:
        process_env.update(env)

    stdout_file = None
    stderr_file = None

    try:
        if stdio_mode == StdioMode.SEPARATE:
            stdout_path = str(out_dir / f"job_{job_id}.stdout")
            stderr_path = str(out_dir / f"job_{job_id}.stderr")
            stdout_file = open(stdout_path, "w")
            stderr_file = open(stderr_path, "w")
            stdout_target = stdout_file
            stderr_target = stderr_file
        elif stdio_mode == StdioMode.COMBINED:
            stdout_path = str(out_dir / f"job_{job_id}.log")
            stdout_file = open(stdout_path, "w")
            stdout_target = stdout_file
            stderr_target = stdout_file
        elif stdio_mode == StdioMode.NO_STDOUT:
            stderr_path = str(out_dir / f"job_{job_id}.stderr")
            stderr_file = open(stderr_path, "w")
            stdout_target = asyncio.subprocess.DEVNULL
            stderr_target = stderr_file
        elif stdio_mode == StdioMode.NO_STDERR:
            stdout_path = str(out_dir / f"job_{job_id}.stdout")
            stdout_file = open(stdout_path, "w")
            stdout_target = stdout_file
            stderr_target = asyncio.subprocess.DEVNULL
        else:  # NONE
            stdout_target = asyncio.subprocess.DEVNULL
            stderr_target = asyncio.subprocess.DEVNULL

        start_time = time.monotonic()

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=stdout_target,
            stderr=stderr_target,
            cwd=work_dir,
            env=process_env,
        )

        try:
            if walltime_seconds:
                await asyncio.wait_for(process.wait(), timeout=walltime_seconds)
            else:
                await process.wait()
        except TimeoutError:
            logger.warning(
                "Job %d exceeded walltime (%.0fs), terminating", job_id, walltime_seconds
            )
            try:
                process.terminate()
                # Give 10s for graceful shutdown
                try:
                    await asyncio.wait_for(process.wait(), timeout=10)
                except TimeoutError:
                    process.kill()
                    await process.wait()
            except ProcessLookupError:
                pass

        elapsed = time.monotonic() - start_time
        return_code = process.returncode if process.returncode is not None else -1

        logger.debug(
            "Job %d completed: return_code=%d elapsed=%.1fs",
            job_id,
            return_code,
            elapsed,
        )

        return CommandResult(
            return_code=return_code,
            exec_time_seconds=elapsed,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

    finally:
        if stdout_file:
            stdout_file.close()
        if stderr_file and stderr_file is not stdout_file:
            stderr_file.close()
