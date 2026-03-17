# CLI Cheat Sheet

## Global Options

```console
torcpy --url http://host:8080/torcpy/v1 <command>
torcpy --verbose <command>
```

Set `TORCPY_API_URL` to avoid passing `--url` every time.

---

## Server

```console
torcpy server run                              # Start server (localhost:8080, torcpy.db)
torcpy server run --host 0.0.0.0              # Bind to all interfaces
torcpy server run --port 9090                 # Custom port
torcpy server run --db /data/workflows.db     # Custom database path
torcpy server run --verbose                   # Debug logging
```

---

## Quick Commands

```console
torcpy run pipeline.yaml          # Create workflow from spec and run locally
torcpy run 42                     # Run existing workflow by ID
torcpy submit pipeline.yaml       # Create workflow and initialize (no execution)
```

---

## Workflows

```console
torcpy workflows create pipeline.yaml         # Create from spec file
torcpy workflows list                         # List all workflows
torcpy workflows list --format json           # JSON output
torcpy workflows get 42                       # Get workflow details
torcpy workflows status 42                    # Show job counts by status
torcpy workflows run 42                       # Run locally
torcpy workflows run 42 --output-dir /logs    # Custom log directory
torcpy workflows initialize 42               # Build dependency graph only
torcpy workflows cancel 42                   # Cancel all pending/ready jobs
torcpy workflows reset 42                    # Reset all jobs to uninitialized
torcpy workflows delete 42                   # Delete workflow and all data
```

---

## Jobs

```console
torcpy jobs list 42                   # List all jobs in workflow 42
torcpy jobs list 42 --status 6        # List only failed jobs
torcpy jobs list 42 --status 2        # List only ready jobs
torcpy jobs list 42 --format json     # JSON output
torcpy jobs get 42 7                  # Get details for job 7 in workflow 42
torcpy jobs update 42 7 --status 0   # Reset job 7 to uninitialized
torcpy jobs update 42 7 --status 2   # Force job 7 to ready
```

---

## Reports

```console
torcpy reports summary 42             # Execution summary
torcpy reports results 42             # Per-job result metrics
torcpy reports results 42 --format json
```

---

## Job Status Codes

| Code | Name |
|:---:|---|
| 0 | uninitialized |
| 1 | blocked |
| 2 | ready |
| 3 | pending |
| 4 | running |
| 5 | completed |
| 6 | failed |
| 7 | canceled |
| 8 | terminated |
| 9 | disabled |
| 10 | pending_failed |
