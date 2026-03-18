"""Background tasks for deferred job unblocking."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from sqlalchemy import select, text, update

from torcpy.server.orm import JobORM

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)


class BackgroundUnblockTask:
    """Periodically processes completed/failed/canceled jobs to unblock dependents."""

    def __init__(self, session_factory: async_sessionmaker, interval: float = 1.0) -> None:
        self.session_factory = session_factory
        self.interval = interval
        self._task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._event = asyncio.Event()
        self._running = False

    def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Background unblock task started (interval=%.1fs)", self.interval)

    async def stop(self) -> None:
        self._running = False
        self._event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass
        logger.info("Background unblock task stopped")

    def signal(self) -> None:
        """Signal that there are jobs to process."""
        self._event.set()

    async def _run(self) -> None:
        while self._running:
            try:
                await asyncio.wait_for(self._event.wait(), timeout=self.interval)
            except TimeoutError:
                pass
            self._event.clear()

            if not self._running:
                break

            try:
                await self._process_pending_unblocks()
            except Exception:
                logger.exception("Error in background unblock task")

    async def _process_pending_unblocks(self) -> None:
        """Find completed/failed/canceled/terminated jobs and unblock their dependents."""
        async with self.session_factory() as session:
            stmt = select(JobORM.id, JobORM.workflow_id, JobORM.status).where(
                JobORM.status.in_([5, 6, 7, 8]),
                JobORM.unblocking_processed == 0,
            )
            rows = (await session.execute(stmt)).all()

            if not rows:
                return

            logger.debug("Processing %d pending unblocks", len(rows))

            for row in rows:
                job_id, workflow_id, status = row[0], row[1], row[2]
                try:
                    # Use BEGIN IMMEDIATE for write safety
                    await session.execute(text("BEGIN IMMEDIATE"))
                    try:
                        if status == 5:  # COMPLETED
                            await self._unblock_dependents(session, workflow_id, job_id)
                        elif status in (6, 7, 8):  # FAILED, CANCELED, TERMINATED
                            await self._handle_failed_dependency(session, workflow_id, job_id)

                        await session.execute(
                            update(JobORM).where(JobORM.id == job_id).values(unblocking_processed=1)
                        )
                        await session.execute(text("COMMIT"))
                    except Exception:
                        await session.execute(text("ROLLBACK"))
                        raise
                except Exception:
                    logger.exception(
                        "Error processing unblock for workflow_id=%d job_id=%d",
                        workflow_id,
                        job_id,
                    )

    async def _unblock_dependents(
        self, session: object, workflow_id: int, completed_job_id: int
    ) -> None:
        """Check if any blocked jobs can now be unblocked."""
        from sqlalchemy.ext.asyncio import AsyncSession

        assert isinstance(session, AsyncSession)

        dependent_rows = (
            await session.execute(
                text(
                    """
                    SELECT DISTINCT jdo.job_id
                    FROM job_depends_on jdo
                    JOIN job j ON j.id = jdo.job_id
                    WHERE jdo.depends_on_job_id = :job_id AND j.status = 1
                    """
                ),
                {"job_id": completed_job_id},
            )
        ).all()

        for dep_row in dependent_rows:
            dep_job_id = dep_row[0]
            unmet = (
                await session.execute(
                    text(
                        """
                        SELECT 1 FROM job_depends_on jdo
                        JOIN job j ON j.id = jdo.depends_on_job_id
                        WHERE jdo.job_id = :job_id AND j.status != 5
                        LIMIT 1
                        """
                    ),
                    {"job_id": dep_job_id},
                )
            ).first()
            if unmet is None:
                await session.execute(
                    update(JobORM)
                    .where(JobORM.id == dep_job_id, JobORM.status == 1)
                    .values(status=2)
                )
                logger.debug("Unblocked job workflow_id=%d job_id=%d", workflow_id, dep_job_id)

    async def _handle_failed_dependency(
        self, session: object, workflow_id: int, failed_job_id: int
    ) -> None:
        """Cancel jobs that depend on a failed job if cancel_on_blocking_job_failure is set."""
        from sqlalchemy.ext.asyncio import AsyncSession

        assert isinstance(session, AsyncSession)

        dependent_rows = (
            await session.execute(
                text(
                    """
                    SELECT DISTINCT jdo.job_id
                    FROM job_depends_on jdo
                    JOIN job j ON j.id = jdo.job_id
                    WHERE jdo.depends_on_job_id = :job_id
                      AND j.status IN (0, 1, 2)
                      AND j.cancel_on_blocking_job_failure = 1
                    """
                ),
                {"job_id": failed_job_id},
            )
        ).all()

        for dep_row in dependent_rows:
            dep_job_id = dep_row[0]
            await session.execute(update(JobORM).where(JobORM.id == dep_job_id).values(status=7))
            logger.debug(
                "Canceled dependent job workflow_id=%d job_id=%d (dependency %d failed)",
                workflow_id,
                dep_job_id,
                failed_job_id,
            )
