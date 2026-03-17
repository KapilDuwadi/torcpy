"""Background tasks for deferred job unblocking."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torcpy.server.database import Database

logger = logging.getLogger(__name__)


class BackgroundUnblockTask:
    """Periodically processes completed/failed/canceled jobs to unblock dependents."""

    def __init__(self, db: Database, interval: float = 1.0) -> None:
        self.db = db
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
            except asyncio.TimeoutError:
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
            except asyncio.TimeoutError:
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
        # Find jobs that completed but haven't had dependents unblocked
        rows = await self.db.fetchall(
            """
            SELECT id, workflow_id, status FROM job
            WHERE status IN (5, 6, 7, 8) AND unblocking_processed = 0
            """
        )

        if not rows:
            return

        logger.debug("Processing %d pending unblocks", len(rows))

        for row in rows:
            job_id = row["id"]
            workflow_id = row["workflow_id"]
            status = row["status"]

            try:
                async with self.db.write_transaction() as conn:
                    if status == 5:  # COMPLETED
                        await self._unblock_dependents(conn, workflow_id, job_id)
                    elif status in (6, 7, 8):  # FAILED, CANCELED, TERMINATED
                        await self._handle_failed_dependency(
                            conn, workflow_id, job_id
                        )

                    await conn.execute(
                        "UPDATE job SET unblocking_processed = 1 WHERE id = ?",
                        (job_id,),
                    )
            except Exception:
                logger.exception(
                    "Error processing unblock for workflow_id=%d job_id=%d",
                    workflow_id,
                    job_id,
                )

    async def _unblock_dependents(
        self, conn: object, workflow_id: int, completed_job_id: int
    ) -> None:
        """Check if any blocked jobs can now be unblocked."""
        # Find jobs that depend on the completed job
        dependent_rows = await self.db.fetchall(
            """
            SELECT DISTINCT jdo.job_id
            FROM job_depends_on jdo
            JOIN job j ON j.id = jdo.job_id
            WHERE jdo.depends_on_job_id = ? AND j.status = 1
            """,
            (completed_job_id,),
        )

        for dep_row in dependent_rows:
            dep_job_id = dep_row["job_id"]
            # Check if ALL dependencies of this job are completed
            unmet = await self.db.fetchone(
                """
                SELECT 1 FROM job_depends_on jdo
                JOIN job j ON j.id = jdo.depends_on_job_id
                WHERE jdo.job_id = ? AND j.status != 5
                LIMIT 1
                """,
                (dep_job_id,),
            )
            if unmet is None:
                # All deps completed — mark as ready
                await self.db.execute(
                    "UPDATE job SET status = 2 WHERE id = ? AND status = 1",
                    (dep_job_id,),
                )
                logger.debug(
                    "Unblocked job workflow_id=%d job_id=%d", workflow_id, dep_job_id
                )

    async def _handle_failed_dependency(
        self, conn: object, workflow_id: int, failed_job_id: int
    ) -> None:
        """Cancel jobs that depend on a failed job if cancel_on_blocking_job_failure is set."""
        dependent_rows = await self.db.fetchall(
            """
            SELECT DISTINCT jdo.job_id
            FROM job_depends_on jdo
            JOIN job j ON j.id = jdo.job_id
            WHERE jdo.depends_on_job_id = ?
              AND j.status IN (0, 1, 2)
              AND j.cancel_on_blocking_job_failure = 1
            """,
            (failed_job_id,),
        )

        for dep_row in dependent_rows:
            dep_job_id = dep_row["job_id"]
            await self.db.execute(
                "UPDATE job SET status = 7 WHERE id = ?",  # CANCELED
                (dep_job_id,),
            )
            logger.debug(
                "Canceled dependent job workflow_id=%d job_id=%d (dependency %d failed)",
                workflow_id,
                dep_job_id,
                failed_job_id,
            )
