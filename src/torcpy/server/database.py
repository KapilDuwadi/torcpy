"""SQLite database layer with async support."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import aiosqlite

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 10_000
MAX_LIMIT = 10_000


class Database:
    """Async SQLite database wrapper."""

    def __init__(self, db_path: str = "torcpy.db") -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.execute("PRAGMA busy_timeout=5000")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected")
        return self._conn

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Regular transaction context manager."""
        await self.conn.execute("BEGIN")
        try:
            yield self.conn
            await self.conn.execute("COMMIT")
        except Exception:
            await self.conn.execute("ROLLBACK")
            raise

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Write transaction with BEGIN IMMEDIATE to prevent concurrent writes."""
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
            await self.conn.execute("COMMIT")
        except Exception:
            await self.conn.execute("ROLLBACK")
            raise

    async def execute(
        self, sql: str, params: tuple | dict | None = None
    ) -> aiosqlite.Cursor:
        return await self.conn.execute(sql, params or ())

    async def executemany(
        self, sql: str, params_seq: list[tuple | dict]
    ) -> aiosqlite.Cursor:
        return await self.conn.executemany(sql, params_seq)

    async def fetchone(
        self, sql: str, params: tuple | dict | None = None
    ) -> aiosqlite.Row | None:
        cursor = await self.execute(sql, params)
        return await cursor.fetchone()

    async def fetchall(
        self, sql: str, params: tuple | dict | None = None
    ) -> list[aiosqlite.Row]:
        cursor = await self.execute(sql, params)
        return await cursor.fetchall()

    async def insert(self, sql: str, params: tuple | dict | None = None) -> int:
        cursor = await self.execute(sql, params)
        await self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def init_schema(self) -> None:
        """Create all tables if they don't exist."""
        await self.conn.executescript(SCHEMA_SQL)
        logger.info("Database schema initialized")


def clamp_pagination(offset: int | None, limit: int | None) -> tuple[int, int]:
    """Clamp pagination parameters to valid ranges."""
    off = max(0, offset or 0)
    lim = min(MAX_LIMIT, max(1, limit or DEFAULT_LIMIT))
    return off, lim


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS workflow (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    user TEXT,
    timestamp REAL,
    metadata TEXT,
    slurm_defaults TEXT,
    resource_monitor_config TEXT,
    execution_config TEXT,
    use_pending_failed INTEGER NOT NULL DEFAULT 0,
    project TEXT
);

CREATE TABLE IF NOT EXISTS workflow_status (
    workflow_id INTEGER PRIMARY KEY REFERENCES workflow(id) ON DELETE CASCADE,
    run_id INTEGER NOT NULL DEFAULT 0,
    is_archived INTEGER NOT NULL DEFAULT 0,
    is_canceled INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    command TEXT,
    status INTEGER NOT NULL DEFAULT 0,
    resource_requirements_id INTEGER REFERENCES resource_requirements(id),
    scheduler_id INTEGER,
    failure_handler_id INTEGER REFERENCES failure_handler(id),
    attempt_id INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0,
    unblocking_processed INTEGER NOT NULL DEFAULT 1,
    cancel_on_blocking_job_failure INTEGER NOT NULL DEFAULT 0,
    supports_termination INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_job_workflow_id ON job(workflow_id);
CREATE INDEX IF NOT EXISTS idx_job_status ON job(status);
CREATE INDEX IF NOT EXISTS idx_job_workflow_status ON job(workflow_id, status);
CREATE INDEX IF NOT EXISTS idx_job_workflow_status_priority
    ON job(workflow_id, status, priority DESC);
CREATE INDEX IF NOT EXISTS idx_job_unblocking_pending
    ON job(workflow_id, unblocking_processed) WHERE status IN (5,6,7,8) AND unblocking_processed=0;

CREATE TABLE IF NOT EXISTS job_internal (
    job_id INTEGER PRIMARY KEY REFERENCES job(id) ON DELETE CASCADE,
    input_hash TEXT,
    active_compute_node_id INTEGER
);

CREATE TABLE IF NOT EXISTS resource_requirements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    num_cpus INTEGER,
    num_gpus INTEGER,
    num_nodes INTEGER,
    memory TEXT,
    runtime TEXT,
    memory_bytes INTEGER,
    runtime_s REAL
);
CREATE INDEX IF NOT EXISTS idx_rr_workflow_id ON resource_requirements(workflow_id);

CREATE TABLE IF NOT EXISTS file (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    path TEXT,
    st_mtime REAL
);
CREATE INDEX IF NOT EXISTS idx_file_workflow_id ON file(workflow_id);

CREATE TABLE IF NOT EXISTS user_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    data TEXT,
    is_ephemeral INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_user_data_workflow_id ON user_data(workflow_id);

CREATE TABLE IF NOT EXISTS job_depends_on (
    job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    depends_on_job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    workflow_id INTEGER NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    PRIMARY KEY (job_id, depends_on_job_id)
);
CREATE INDEX IF NOT EXISTS idx_job_depends_on_depends_on_job_id
    ON job_depends_on(depends_on_job_id);
CREATE INDEX IF NOT EXISTS idx_job_depends_on_workflow
    ON job_depends_on(workflow_id);

CREATE TABLE IF NOT EXISTS job_input_file (
    job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    file_id INTEGER NOT NULL REFERENCES file(id) ON DELETE CASCADE,
    workflow_id INTEGER NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    PRIMARY KEY (job_id, file_id)
);

CREATE TABLE IF NOT EXISTS job_output_file (
    job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    file_id INTEGER NOT NULL REFERENCES file(id) ON DELETE CASCADE,
    workflow_id INTEGER NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    PRIMARY KEY (job_id, file_id)
);

CREATE TABLE IF NOT EXISTS job_input_user_data (
    job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    user_data_id INTEGER NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
    PRIMARY KEY (job_id, user_data_id)
);

CREATE TABLE IF NOT EXISTS job_output_user_data (
    job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    user_data_id INTEGER NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
    PRIMARY KEY (job_id, user_data_id)
);

CREATE TABLE IF NOT EXISTS compute_node (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    hostname TEXT NOT NULL,
    pid INTEGER,
    start_time REAL,
    is_active INTEGER NOT NULL DEFAULT 1,
    num_cpus INTEGER,
    memory_gb REAL,
    num_gpus INTEGER,
    num_nodes INTEGER,
    time_limit REAL,
    scheduler_config_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_compute_node_workflow_id ON compute_node(workflow_id);

CREATE TABLE IF NOT EXISTS result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    run_id INTEGER NOT NULL DEFAULT 0,
    compute_node_id INTEGER REFERENCES compute_node(id),
    return_code INTEGER,
    exec_time_minutes REAL,
    completion_time REAL,
    status TEXT,
    peak_memory_bytes INTEGER,
    avg_memory_bytes INTEGER,
    peak_cpu_percent REAL,
    avg_cpu_percent REAL,
    UNIQUE(job_id, run_id)
);
CREATE INDEX IF NOT EXISTS idx_result_workflow_job ON result(workflow_id, job_id);

CREATE TABLE IF NOT EXISTS event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    timestamp INTEGER,
    data TEXT
);
CREATE INDEX IF NOT EXISTS idx_event_workflow_id ON event(workflow_id);

CREATE TABLE IF NOT EXISTS failure_handler (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    rules TEXT,
    default_max_retries INTEGER NOT NULL DEFAULT 0,
    default_recovery_command TEXT
);
CREATE INDEX IF NOT EXISTS idx_failure_handler_workflow_id ON failure_handler(workflow_id);

CREATE TABLE IF NOT EXISTS local_scheduler (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    num_cpus INTEGER,
    memory TEXT
);

CREATE TABLE IF NOT EXISTS slurm_scheduler (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    account TEXT,
    partition TEXT,
    slurm_config TEXT
);

CREATE TABLE IF NOT EXISTS workflow_action (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    trigger_type TEXT NOT NULL,
    action_type TEXT NOT NULL,
    job_ids TEXT,
    job_name_regex TEXT,
    commands TEXT,
    trigger_count INTEGER NOT NULL DEFAULT 0,
    required_triggers INTEGER NOT NULL DEFAULT 1,
    executed INTEGER NOT NULL DEFAULT 0,
    executed_at REAL,
    persistent INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_workflow_action_workflow_id ON workflow_action(workflow_id);

CREATE TABLE IF NOT EXISTS access_group (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS access_group_member (
    group_id INTEGER NOT NULL REFERENCES access_group(id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    PRIMARY KEY (group_id, username)
);

CREATE TABLE IF NOT EXISTS workflow_access_group (
    workflow_id INTEGER NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    group_id INTEGER NOT NULL REFERENCES access_group(id) ON DELETE CASCADE,
    PRIMARY KEY (workflow_id, group_id)
);
"""
