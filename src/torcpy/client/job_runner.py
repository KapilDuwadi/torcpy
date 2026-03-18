"""Local job runner with resource management.

Polls the server for ready jobs, executes them locally with resource tracking,
and reports results back.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from dataclasses import dataclass

from torcpy.client.api_client import TorcClient
from torcpy.client.async_command import run_command
from torcpy.client.resource_tracker import ResourceTracker
from torcpy.models import Job, ResourceRequirements, ResultCreate
from torcpy.models.enums import JobStatus, StdioMode

logger = logging.getLogger(__name__)


@dataclass
class JobRunnerConfig:
    """Configuration for the job runner."""

    poll_interval: float = 2.0
    max_parallel_jobs: int = 0  # 0 = unlimited
    output_dir: str = "output"
    stdio_mode: StdioMode = StdioMode.SEPARATE
    idle_timeout: float = 0  # 0 = no timeout
    claim_batch_size: int = 5


class JobRunner:
    """Runs workflow jobs locally with resource management."""

    def __init__(
        self,
        client: TorcClient,
        workflow_id: int,
        config: JobRunnerConfig | None = None,
    ) -> None:
        self.client = client
        self.workflow_id = workflow_id
        self.config = config or JobRunnerConfig()
        self.resources = ResourceTracker.detect_local()
        self._running_tasks: dict[int, asyncio.Task] = {}  # type: ignore[type-arg]
        self._shutdown = False
        self._rr_cache: dict[int, ResourceRequirements] = {}

    async def run(self) -> dict[str, int]:
        """Run the workflow until all jobs complete or an error occurs.

        Returns summary dict with counts of completed, failed, etc.
        """
        logger.info("Starting job runner for workflow %d", self.workflow_id)

        # Initialize workflow
        init_result = await self.client.initialize_workflow(self.workflow_id)
        logger.info(
            "Initialized: %d ready, %d blocked",
            init_result.get("ready_jobs", 0),
            init_result.get("blocked_jobs", 0),
        )

        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._handle_shutdown)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        last_activity = time.monotonic()
        stats: dict[str, int] = {"completed": 0, "failed": 0, "canceled": 0}

        while not self._shutdown:
            # Check if workflow is done
            status = await self.client.workflow_status(self.workflow_id)
            if status.get("is_canceled"):
                logger.info("Workflow was canceled")
                break

            counts = status.get("job_status_counts", {})
            total = status.get("total_jobs", 0)
            done = (
                counts.get("completed", 0)
                + counts.get("failed", 0)
                + counts.get("canceled", 0)
                + counts.get("terminated", 0)
                + counts.get("disabled", 0)
            )
            active = counts.get("running", 0) + counts.get("pending", 0)

            if done == total and total > 0 and len(self._running_tasks) == 0:
                logger.info("All %d jobs finished", total)
                stats["completed"] = counts.get("completed", 0)
                stats["failed"] = counts.get("failed", 0)
                stats["canceled"] = counts.get("canceled", 0)
                break

            # Deadlock detection: no active or ready jobs but workflow not done
            if (
                len(self._running_tasks) == 0
                and active == 0
                and counts.get("ready", 0) == 0
                and total > 0
                and done < total
            ):
                blocked = counts.get("blocked", 0)
                logger.warning(
                    "Workflow %d is deadlocked: %d jobs remain blocked with no active work",
                    self.workflow_id,
                    blocked,
                )
                stats["completed"] = counts.get("completed", 0)
                stats["failed"] = counts.get("failed", 0)
                stats["canceled"] = counts.get("canceled", 0)
                break

            # Claim and launch jobs if we have capacity
            can_launch = True
            if self.config.max_parallel_jobs > 0:
                can_launch = len(self._running_tasks) < self.config.max_parallel_jobs

            if can_launch and counts.get("ready", 0) > 0:
                claimed = await self.client.claim_next_jobs(
                    self.workflow_id, count=self.config.claim_batch_size
                )
                if claimed:
                    last_activity = time.monotonic()
                    for job in claimed:
                        rr = await self._get_resource_requirements(job)
                        if self.resources.can_fit(rr):
                            self.resources.allocate(job.id, rr)
                            task = asyncio.create_task(self._execute_job(job))
                            self._running_tasks[job.id] = task
                        else:
                            # Can't fit, put back to ready
                            logger.debug(
                                "Job %d doesn't fit current resources, resetting",
                                job.id,
                            )
                            await self.client.update_job(
                                self.workflow_id,
                                job.id,
                                body=type(
                                    "StatusUpdate",
                                    (),
                                    {"model_dump": lambda self, **kw: {"status": JobStatus.READY}},
                                )(),
                            )

            # Clean up finished tasks
            finished = [jid for jid, task in self._running_tasks.items() if task.done()]
            for jid in finished:
                task = self._running_tasks.pop(jid)
                self.resources.release(jid)
                try:
                    task.result()  # Raise any exceptions
                except Exception:
                    logger.exception("Job %d task failed", jid)

            # Idle timeout check
            if (
                self.config.idle_timeout > 0
                and len(self._running_tasks) == 0
                and time.monotonic() - last_activity > self.config.idle_timeout
            ):
                logger.info("Idle timeout reached, stopping")
                break

            await asyncio.sleep(self.config.poll_interval)

        # Wait for running tasks to complete
        if self._running_tasks:
            logger.info("Waiting for %d running jobs to complete...", len(self._running_tasks))
            await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)

        return stats

    async def _get_resource_requirements(self, job: Job) -> ResourceRequirements | None:
        if job.resource_requirements_id is None:
            return None
        if job.resource_requirements_id in self._rr_cache:
            return self._rr_cache[job.resource_requirements_id]

        rr_data = await self.client.list_resource_requirements(self.workflow_id)
        for item in rr_data.get("items", []):
            rr = ResourceRequirements.model_validate(item)
            self._rr_cache[rr.id] = rr

        return self._rr_cache.get(job.resource_requirements_id)

    async def _execute_job(self, job: Job) -> None:
        """Execute a single job."""
        logger.info("Running job %d: %s", job.id, job.name)

        # Update to RUNNING
        from torcpy.models.job import JobUpdate

        await self.client.update_job(
            self.workflow_id,
            job.id,
            JobUpdate(status=JobStatus.RUNNING),
        )

        if not job.command:
            logger.warning("Job %d has no command, marking completed", job.id)
            await self.client.complete_job(self.workflow_id, job.id, status=JobStatus.COMPLETED)
            return

        try:
            result = await run_command(
                job.command,
                job_id=job.id,
                output_dir=self.config.output_dir,
                stdio_mode=self.config.stdio_mode,
            )

            final_status = JobStatus.COMPLETED if result.return_code == 0 else JobStatus.FAILED

            # Create result record
            await self.client.create_result(
                self.workflow_id,
                ResultCreate(
                    workflow_id=self.workflow_id,
                    job_id=job.id,
                    return_code=result.return_code,
                    exec_time_minutes=result.exec_time_seconds / 60,
                    completion_time=time.time(),
                    status=final_status.name.lower(),
                ),
            )

            await self.client.complete_job(self.workflow_id, job.id, status=final_status)
            logger.info(
                "Job %d (%s) %s (%.1fs)",
                job.id,
                job.name,
                final_status.name.lower(),
                result.exec_time_seconds,
            )

        except Exception:
            logger.exception("Job %d execution error", job.id)
            await self.client.complete_job(self.workflow_id, job.id, status=JobStatus.FAILED)

    def _handle_shutdown(self) -> None:
        logger.info("Shutdown signal received")
        self._shutdown = True
