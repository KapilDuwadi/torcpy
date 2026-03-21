"""Main CLI entry point using rich-click."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Callable

import rich_click as click
from rich.console import Console
from rich.table import Table

from torcpy.models.job import Job

console = Console()


# ── Output renderer registries ──


async def _render_create_json(client: object, wf_id: int, spec_name: str) -> None:
    from torcpy.client import TorcClient

    wf = await client.get_workflow(wf_id)  # type: ignore[union-attr]
    console.print_json(wf.model_dump_json())


async def _render_create_table(client: object, wf_id: int, spec_name: str) -> None:
    console.print(f"Created workflow [cyan]{wf_id}[/cyan]: {spec_name}")


_WORKFLOW_CREATE_RENDERERS: dict[str, Callable] = {
    "json": _render_create_json,
    "table": _render_create_table,
}


def _build_jobs_table(jobs: list[Job]) -> Table:
    table = Table(title="Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Priority")
    table.add_column("Command")
    for job in jobs:
        cmd = job.command or ""
        if len(cmd) > 50:
            cmd = cmd[:47] + "..."
        table.add_row(
            str(job.id),
            job.name,
            job.status.name.lower(),
            str(job.priority),
            cmd,
        )
    return table


_JOB_RENDERERS: dict[str, Callable[[list[Job]], None]] = {
    "json": lambda jobs: console.print_json(
        json.dumps([j.model_dump() for j in jobs])
    ),
    "table": lambda jobs: console.print(_build_jobs_table(jobs)),
}

DEFAULT_URL = "http://localhost:8080/torcpy/v1"


def get_url(ctx: click.Context) -> str:
    return ctx.obj.get("url") or os.environ.get("TORCPY_API_URL", DEFAULT_URL)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def run_async(coro):  # type: ignore[no-untyped-def]
    """Run an async function from sync context."""
    return asyncio.run(coro)


# ── Root Group ──


@click.group()
@click.option("--url", default=None, help="Server URL (or set TORCPY_API_URL)")
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx: click.Context, url: str | None, verbose: bool) -> None:
    """TorcPy - Distributed workflow orchestration."""
    ctx.ensure_object(dict)
    ctx.obj["url"] = url
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)


# ── Server Commands ──


@cli.group()
def server() -> None:
    """Server management commands."""


@server.command("run")
@click.option("--host", default="localhost", help="Host to bind to")
@click.option("--port", default=8080, type=int, help="Port to listen on")
@click.option("--db", default="torcpy.db", help="SQLite database path")
@click.pass_context
def server_run(ctx: click.Context, host: str, port: int, db: str) -> None:
    """Start the TorcPy server."""
    import uvicorn

    from torcpy.server.app import create_app

    app = create_app(db_path=db)
    console.print(f"Starting TorcPy server on {host}:{port} (db={db})")
    verbose = ctx.obj.get("verbose", False)
    uvicorn.run(app, host=host, port=port, log_level="debug" if verbose else "info")


# ── Top-level Convenience Commands ──


@cli.command("run")
@click.argument("spec_or_id")
@click.option("-o", "--output-dir", default="output", help="Output directory for job logs")
@click.pass_context
def run_cmd(ctx: click.Context, spec_or_id: str, output_dir: str) -> None:
    """Create a workflow from spec and run it locally."""

    async def _run() -> None:
        from torcpy.client import JobRunner, TorcClient, WorkflowSpec, create_workflow_from_spec
        from torcpy.client.job_runner import JobRunnerConfig

        async with TorcClient(get_url(ctx)) as client:
            if Path(spec_or_id).exists():
                spec = WorkflowSpec.from_file(spec_or_id)
                wf_id = await create_workflow_from_spec(client, spec)
                console.print(f"Created workflow {wf_id}")
            else:
                wf_id = int(spec_or_id)

            config = JobRunnerConfig(output_dir=output_dir)
            runner = JobRunner(client, wf_id, config)
            stats = await runner.run()

            console.print(f"\nWorkflow {wf_id} finished:")
            console.print(f"  Completed: {stats.get('completed', 0)}")
            console.print(f"  Failed:    {stats.get('failed', 0)}")
            console.print(f"  Canceled:  {stats.get('canceled', 0)}")

    run_async(_run())


@cli.command("submit")
@click.argument("spec_or_id")
@click.pass_context
def submit_cmd(ctx: click.Context, spec_or_id: str) -> None:
    """Create a workflow from spec and submit (initialize without running)."""

    async def _submit() -> None:
        from torcpy.client import TorcClient, WorkflowSpec, create_workflow_from_spec

        async with TorcClient(get_url(ctx)) as client:
            if Path(spec_or_id).exists():
                spec = WorkflowSpec.from_file(spec_or_id)
                wf_id = await create_workflow_from_spec(client, spec)
                console.print(f"Created workflow {wf_id}")
            else:
                wf_id = int(spec_or_id)

            result = await client.initialize_workflow(wf_id)
            console.print(f"Initialized workflow {wf_id}")
            console.print(
                f"  Ready: {result.get('ready_jobs', 0)}, Blocked: {result.get('blocked_jobs', 0)}"
            )

    run_async(_submit())


# ── Workflow Commands ──


@cli.group()
def workflows() -> None:
    """Workflow management commands."""


@workflows.command("create")
@click.argument("spec_file", type=click.Path(exists=True))
@click.option("-f", "--format", "fmt", default="table", help="Output format: table or json")
@click.pass_context
def workflows_create(ctx: click.Context, spec_file: str, fmt: str) -> None:
    """Create a workflow from a specification file."""

    async def _create() -> None:
        from torcpy.client import TorcClient, WorkflowSpec, create_workflow_from_spec

        renderer = _WORKFLOW_CREATE_RENDERERS.get(fmt)
        if renderer is None:
            raise click.UsageError(
                f"Unknown format {fmt!r}. Choose: {', '.join(_WORKFLOW_CREATE_RENDERERS)}"
            )
        async with TorcClient(get_url(ctx)) as client:
            spec = WorkflowSpec.from_file(spec_file)
            wf_id = await create_workflow_from_spec(client, spec)
            await renderer(client, wf_id, spec.name)

    run_async(_create())


@workflows.command("list")
@click.option("-f", "--format", "fmt", default="table", help="Output format: table or json")
@click.pass_context
def workflows_list(ctx: click.Context, fmt: str) -> None:
    """List all workflows."""

    async def _list() -> None:
        from torcpy.client import TorcClient

        async with TorcClient(get_url(ctx)) as client:
            result = await client.list_workflows()
            items = result.get("items", [])
            if fmt == "json":
                console.print_json(json.dumps(items))
            else:
                table = Table(title="Workflows")
                table.add_column("ID", style="cyan")
                table.add_column("Name")
                table.add_column("User")
                table.add_column("Project")
                for item in items:
                    table.add_row(
                        str(item["id"]),
                        item["name"],
                        item.get("user", ""),
                        item.get("project") or "",
                    )
                console.print(table)

    run_async(_list())


@workflows.command("get")
@click.argument("workflow_id", type=int)
@click.option("-f", "--format", "fmt", default="table", help="Output format: table or json")
@click.pass_context
def workflows_get(ctx: click.Context, workflow_id: int, fmt: str) -> None:
    """Get workflow details."""

    async def _get() -> None:
        from torcpy.client import TorcClient

        async with TorcClient(get_url(ctx)) as client:
            wf = await client.get_workflow(workflow_id)
            if fmt == "json":
                console.print_json(wf.model_dump_json())
            else:
                console.print(f"[bold]Workflow {wf.id}[/bold]: {wf.name}")
                console.print(f"  User: {wf.user}")
                console.print(f"  Project: {wf.project}")
                if wf.status:
                    console.print(f"  Run ID: {wf.status.run_id}")
                    console.print(f"  Canceled: {wf.status.is_canceled}")

    run_async(_get())


@workflows.command("status")
@click.argument("workflow_id", type=int)
@click.option("-f", "--format", "fmt", default="table", help="Output format: table or json")
@click.pass_context
def workflows_status(ctx: click.Context, workflow_id: int, fmt: str) -> None:
    """Show workflow status with job counts."""

    async def _status() -> None:
        from torcpy.client import TorcClient

        async with TorcClient(get_url(ctx)) as client:
            status = await client.workflow_status(workflow_id)
            if fmt == "json":
                console.print_json(json.dumps(status))
            else:
                console.print(f"[bold]Workflow {workflow_id}[/bold]")
                console.print(f"  Run ID: {status.get('run_id', 0)}")
                console.print(f"  Canceled: {status.get('is_canceled', False)}")
                console.print(f"  Total jobs: {status.get('total_jobs', 0)}")
                console.print("  Job status:")
                for name, count in status.get("job_status_counts", {}).items():
                    console.print(f"    {name}: {count}")

    run_async(_status())


@workflows.command("delete")
@click.argument("workflow_id", type=int)
@click.pass_context
def workflows_delete(ctx: click.Context, workflow_id: int) -> None:
    """Delete a workflow."""

    async def _delete() -> None:
        from torcpy.client import TorcClient

        async with TorcClient(get_url(ctx)) as client:
            await client.delete_workflow(workflow_id)
            console.print(f"Deleted workflow {workflow_id}")

    run_async(_delete())


@workflows.command("cancel")
@click.argument("workflow_id", type=int)
@click.pass_context
def workflows_cancel(ctx: click.Context, workflow_id: int) -> None:
    """Cancel a workflow."""

    async def _cancel() -> None:
        from torcpy.client import TorcClient

        async with TorcClient(get_url(ctx)) as client:
            await client.cancel_workflow(workflow_id)
            console.print(f"Canceled workflow {workflow_id}")

    run_async(_cancel())


@workflows.command("initialize")
@click.argument("workflow_id", type=int)
@click.pass_context
def workflows_initialize(ctx: click.Context, workflow_id: int) -> None:
    """Initialize workflow dependencies."""

    async def _init() -> None:
        from torcpy.client import TorcClient

        async with TorcClient(get_url(ctx)) as client:
            result = await client.initialize_workflow(workflow_id)
            console.print(f"Initialized workflow {workflow_id}")
            console.print(
                f"  Ready: {result.get('ready_jobs', 0)}, Blocked: {result.get('blocked_jobs', 0)}"
            )

    run_async(_init())


@workflows.command("reset")
@click.argument("workflow_id", type=int)
@click.pass_context
def workflows_reset(ctx: click.Context, workflow_id: int) -> None:
    """Reset a workflow to re-run."""

    async def _reset() -> None:
        from torcpy.client import TorcClient

        async with TorcClient(get_url(ctx)) as client:
            await client.reset_workflow(workflow_id)
            console.print(f"Reset workflow {workflow_id}")

    run_async(_reset())


@workflows.command("run")
@click.argument("workflow_id", type=int)
@click.option("-o", "--output-dir", default="output", help="Output directory for job logs")
@click.pass_context
def workflows_run(ctx: click.Context, workflow_id: int, output_dir: str) -> None:
    """Run an existing workflow locally."""

    async def _run() -> None:
        from torcpy.client import JobRunner, TorcClient
        from torcpy.client.job_runner import JobRunnerConfig

        async with TorcClient(get_url(ctx)) as client:
            config = JobRunnerConfig(output_dir=output_dir)
            runner = JobRunner(client, workflow_id, config)
            stats = await runner.run()
            console.print(f"\nWorkflow {workflow_id} finished:")
            console.print(f"  Completed: {stats.get('completed', 0)}")
            console.print(f"  Failed:    {stats.get('failed', 0)}")

    run_async(_run())


# ── Job Commands ──


@cli.group()
def jobs() -> None:
    """Job management commands."""


@jobs.command("list")
@click.argument("workflow_id", type=int)
@click.option("-s", "--status", type=int, default=None, help="Filter by status code")
@click.option("-f", "--format", "fmt", default="table", help="Output format: table or json")
@click.pass_context
def jobs_list(ctx: click.Context, workflow_id: int, status: int | None, fmt: str) -> None:
    """List jobs for a workflow."""

    async def _list() -> None:
        from torcpy.client import TorcClient

        renderer = _JOB_RENDERERS.get(fmt)
        if renderer is None:
            raise click.UsageError(
                f"Unknown format {fmt!r}. Choose: {', '.join(_JOB_RENDERERS)}"
            )
        async with TorcClient(get_url(ctx)) as client:
            response = await client.list_jobs(workflow_id, status=status)
        renderer(response.items)

    run_async(_list())


@jobs.command("get")
@click.argument("workflow_id", type=int)
@click.argument("job_id", type=int)
@click.option("-f", "--format", "fmt", default="table", help="Output format: table or json")
@click.pass_context
def jobs_get(ctx: click.Context, workflow_id: int, job_id: int, fmt: str) -> None:
    """Get job details."""

    async def _get() -> None:
        from torcpy.client import TorcClient

        async with TorcClient(get_url(ctx)) as client:
            job = await client.get_job(workflow_id, job_id)
            if fmt == "json":
                console.print_json(job.model_dump_json())
            else:
                console.print(f"[bold]Job {job.id}[/bold]: {job.name}")
                console.print(f"  Status: {job.status.name.lower()}")
                console.print(f"  Command: {job.command}")
                console.print(f"  Priority: {job.priority}")
                if job.depends_on_job_ids:
                    console.print(f"  Depends on: {job.depends_on_job_ids}")

    run_async(_get())


@jobs.command("update")
@click.argument("workflow_id", type=int)
@click.argument("job_id", type=int)
@click.option("-s", "--status", type=int, default=None, help="New status code")
@click.pass_context
def jobs_update(ctx: click.Context, workflow_id: int, job_id: int, status: int | None) -> None:
    """Update a job's status."""

    async def _update() -> None:
        from torcpy.client import TorcClient
        from torcpy.models.enums import JobStatus
        from torcpy.models.job import JobUpdate

        async with TorcClient(get_url(ctx)) as client:
            body = JobUpdate()
            if status is not None:
                body.status = JobStatus(status)
            job = await client.update_job(workflow_id, job_id, body)
            console.print(f"Updated job {job.id}: status={job.status.name.lower()}")

    run_async(_update())


# ── Report Commands ──


@cli.group()
def reports() -> None:
    """Report commands."""


@reports.command("summary")
@click.argument("workflow_id", type=int)
@click.option("-f", "--format", "fmt", default="table", help="Output format: table or json")
@click.pass_context
def reports_summary(ctx: click.Context, workflow_id: int, fmt: str) -> None:
    """Show workflow execution summary."""

    async def _summary() -> None:
        from torcpy.client import TorcClient

        async with TorcClient(get_url(ctx)) as client:
            status = await client.workflow_status(workflow_id)
            results_data = await client.list_results(workflow_id)
            results = results_data.get("items", [])

            if fmt == "json":
                console.print_json(json.dumps({"status": status, "results": results}))
            else:
                console.print(f"[bold]Workflow {workflow_id} Summary[/bold]")
                console.print(f"  Total jobs: {status.get('total_jobs', 0)}")
                for name, count in status.get("job_status_counts", {}).items():
                    console.print(f"  {name}: {count}")

                if results:
                    total_time = sum(r.get("exec_time_minutes", 0) or 0 for r in results)
                    console.print(f"\n  Total execution time: {total_time:.1f} minutes")
                    failures = [r for r in results if r.get("return_code", 0) != 0]
                    if failures:
                        console.print(f"  Failed results: {len(failures)}")

    run_async(_summary())


@reports.command("results")
@click.argument("workflow_id", type=int)
@click.option("-f", "--format", "fmt", default="table", help="Output format: table or json")
@click.pass_context
def reports_results(ctx: click.Context, workflow_id: int, fmt: str) -> None:
    """Show job execution results."""

    async def _results() -> None:
        from torcpy.client import TorcClient

        async with TorcClient(get_url(ctx)) as client:
            results_data = await client.list_results(workflow_id)
            items = results_data.get("items", [])

            if fmt == "json":
                console.print_json(json.dumps(items))
            else:
                table = Table(title=f"Results (workflow {workflow_id})")
                table.add_column("Job ID", style="cyan")
                table.add_column("Return Code")
                table.add_column("Time (min)")
                table.add_column("Status")
                table.add_column("Peak Mem (MB)")
                for item in items:
                    peak_mem = item.get("peak_memory_bytes")
                    mem_str = f"{peak_mem / 1024 / 1024:.1f}" if peak_mem else ""
                    table.add_row(
                        str(item["job_id"]),
                        str(item.get("return_code", "")),
                        f"{item.get('exec_time_minutes', 0):.2f}",
                        item.get("status", ""),
                        mem_str,
                    )
                console.print(table)

    run_async(_results())


if __name__ == "__main__":
    cli()
