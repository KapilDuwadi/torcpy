"""SQLAlchemy ORM models for TorcPy."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ---------------------------------------------------------------------------
# Custom type: JSON stored as TEXT
# ---------------------------------------------------------------------------
class JSONText(String):
    """Marker type — actual serialisation handled by property helpers."""


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------
class Base(AsyncAttrs, DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Helper to create engine + session factory
# ---------------------------------------------------------------------------
def make_engine(db_path: str):
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


def make_session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# JSON helper mixin
# ---------------------------------------------------------------------------
def _json_loads(val: str | None) -> Any:
    if val is None:
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


def _json_dumps(val: Any) -> str | None:
    if val is None:
        return None
    return json.dumps(val)


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class WorkflowORM(Base):
    __tablename__ = "workflow"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    user: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_: Mapped[str | None] = mapped_column("metadata", Text, nullable=True)
    slurm_defaults: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_monitor_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    use_pending_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    project: Mapped[str | None] = mapped_column(Text, nullable=True)

    # relationships
    status: Mapped[WorkflowStatusORM | None] = relationship(
        "WorkflowStatusORM",
        back_populates="workflow",
        uselist=False,
        lazy="joined",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    jobs: Mapped[list[JobORM]] = relationship(
        "JobORM",
        back_populates="workflow",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class WorkflowStatusORM(Base):
    __tablename__ = "workflow_status"

    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), primary_key=True
    )
    run_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_archived: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_canceled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    workflow: Mapped[WorkflowORM] = relationship("WorkflowORM", back_populates="status")


class JobORM(Base):
    __tablename__ = "job"
    __table_args__ = (
        Index("idx_job_workflow_id", "workflow_id"),
        Index("idx_job_status", "status"),
        Index("idx_job_workflow_status", "workflow_id", "status"),
        Index("idx_job_workflow_status_priority", "workflow_id", "status", "priority"),
        Index(
            "idx_job_unblocking_pending",
            "workflow_id",
            "unblocking_processed",
            sqlite_where=text("status IN (5,6,7,8) AND unblocking_processed=0"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    command: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resource_requirements_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("resource_requirements.id"), nullable=True
    )
    scheduler_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_handler_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("failure_handler.id"), nullable=True
    )
    attempt_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unblocking_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cancel_on_blocking_job_failure: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    supports_termination: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    workflow: Mapped[WorkflowORM] = relationship("WorkflowORM", back_populates="jobs")

    # junction relationships (eager-loadable)
    depends_on_links: Mapped[list[JobDependsOnORM]] = relationship(
        "JobDependsOnORM",
        foreign_keys="JobDependsOnORM.job_id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    input_file_links: Mapped[list[JobInputFileORM]] = relationship(
        "JobInputFileORM",
        foreign_keys="JobInputFileORM.job_id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    output_file_links: Mapped[list[JobOutputFileORM]] = relationship(
        "JobOutputFileORM",
        foreign_keys="JobOutputFileORM.job_id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    input_user_data_links: Mapped[list[JobInputUserDataORM]] = relationship(
        "JobInputUserDataORM",
        foreign_keys="JobInputUserDataORM.job_id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    output_user_data_links: Mapped[list[JobOutputUserDataORM]] = relationship(
        "JobOutputUserDataORM",
        foreign_keys="JobOutputUserDataORM.job_id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    internal: Mapped[JobInternalORM | None] = relationship(
        "JobInternalORM", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )


class JobInternalORM(Base):
    __tablename__ = "job_internal"

    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job.id", ondelete="CASCADE"), primary_key=True
    )
    input_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_compute_node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ResourceRequirementsORM(Base):
    __tablename__ = "resource_requirements"
    __table_args__ = (Index("idx_rr_workflow_id", "workflow_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False
    )
    num_cpus: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_gpus: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_nodes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runtime_s: Mapped[float | None] = mapped_column(Float, nullable=True)


class FileORM(Base):
    __tablename__ = "file"
    __table_args__ = (Index("idx_file_workflow_id", "workflow_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    st_mtime: Mapped[float | None] = mapped_column(Float, nullable=True)


class UserDataORM(Base):
    __tablename__ = "user_data"
    __table_args__ = (Index("idx_user_data_workflow_id", "workflow_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_ephemeral: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# ---------------------------------------------------------------------------
# Junction tables
# ---------------------------------------------------------------------------


class JobDependsOnORM(Base):
    __tablename__ = "job_depends_on"
    __table_args__ = (
        Index("idx_job_depends_on_depends_on_job_id", "depends_on_job_id"),
        Index("idx_job_depends_on_workflow", "workflow_id"),
    )

    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job.id", ondelete="CASCADE"), primary_key=True
    )
    depends_on_job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job.id", ondelete="CASCADE"), primary_key=True
    )
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False
    )


class JobInputFileORM(Base):
    __tablename__ = "job_input_file"

    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job.id", ondelete="CASCADE"), primary_key=True
    )
    file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("file.id", ondelete="CASCADE"), primary_key=True
    )
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False
    )


class JobOutputFileORM(Base):
    __tablename__ = "job_output_file"

    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job.id", ondelete="CASCADE"), primary_key=True
    )
    file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("file.id", ondelete="CASCADE"), primary_key=True
    )
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False
    )


class JobInputUserDataORM(Base):
    __tablename__ = "job_input_user_data"

    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job.id", ondelete="CASCADE"), primary_key=True
    )
    user_data_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_data.id", ondelete="CASCADE"), primary_key=True
    )


class JobOutputUserDataORM(Base):
    __tablename__ = "job_output_user_data"

    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job.id", ondelete="CASCADE"), primary_key=True
    )
    user_data_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_data.id", ondelete="CASCADE"), primary_key=True
    )


class ComputeNodeORM(Base):
    __tablename__ = "compute_node"
    __table_args__ = (Index("idx_compute_node_workflow_id", "workflow_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False
    )
    hostname: Mapped[str] = mapped_column(Text, nullable=False)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    num_cpus: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    num_gpus: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_nodes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    scheduler_config_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ResultORM(Base):
    __tablename__ = "result"
    __table_args__ = (
        UniqueConstraint("job_id", "run_id"),
        Index("idx_result_workflow_job", "workflow_id", "job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compute_node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("compute_node.id"), nullable=True
    )
    return_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exec_time_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    completion_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    peak_memory_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_memory_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peak_cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)


class EventORM(Base):
    __tablename__ = "event"
    __table_args__ = (Index("idx_event_workflow_id", "workflow_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data: Mapped[str | None] = mapped_column(Text, nullable=True)


class FailureHandlerORM(Base):
    __tablename__ = "failure_handler"
    __table_args__ = (Index("idx_failure_handler_workflow_id", "workflow_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    default_recovery_command: Mapped[str | None] = mapped_column(Text, nullable=True)


class LocalSchedulerORM(Base):
    __tablename__ = "local_scheduler"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False
    )
    num_cpus: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory: Mapped[str | None] = mapped_column(Text, nullable=True)


class SlurmSchedulerORM(Base):
    __tablename__ = "slurm_scheduler"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False
    )
    account: Mapped[str | None] = mapped_column(Text, nullable=True)
    partition: Mapped[str | None] = mapped_column(Text, nullable=True)
    slurm_config: Mapped[str | None] = mapped_column(Text, nullable=True)


class WorkflowActionORM(Base):
    __tablename__ = "workflow_action"
    __table_args__ = (Index("idx_workflow_action_workflow_id", "workflow_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False
    )
    trigger_type: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    job_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_name_regex: Mapped[str | None] = mapped_column(Text, nullable=True)
    commands: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required_triggers: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    executed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    executed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    persistent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AccessGroupORM(Base):
    __tablename__ = "access_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class AccessGroupMemberORM(Base):
    __tablename__ = "access_group_member"

    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("access_group.id", ondelete="CASCADE"), primary_key=True
    )
    username: Mapped[str] = mapped_column(Text, nullable=False, primary_key=True)


class WorkflowAccessGroupORM(Base):
    __tablename__ = "workflow_access_group"

    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("access_group.id", ondelete="CASCADE"), primary_key=True
    )
