# Architecture Overview

TorcPy uses a **client-server architecture** where a lightweight REST API server manages all
workflow state, and one or more worker processes claim and execute jobs.

## Components

```mermaid
flowchart TB
    subgraph server ["Server Process"]
        API["FastAPI REST API"]
        BG["Background Unblock Task"]
        DB[("SQLite Database")]
        API --> DB
        BG --> DB
    end

    subgraph workers ["Worker Processes"]
        W1["Job Runner 1"]
        W2["Job Runner 2"]
    end

    CLI["CLI / Python Client"]

    CLI -- "HTTP" --> API
    W1 -- "claim_next_jobs\ncomplete_job" --> API
    W2 -- "claim_next_jobs\ncomplete_job" --> API
```

### Server

The server is a **FastAPI** application backed by a **SQLite** database. It exposes a REST API
for all workflow, job, file, and resource management operations.

Key design decisions:

- **WAL mode** — SQLite runs in Write-Ahead Logging mode for concurrent reads.
- **`BEGIN IMMEDIATE`** — Job claiming uses an immediate write lock, preventing two workers from
  claiming the same job.
- **Foreign key cascades** — Deleting a workflow automatically removes all associated jobs,
  files, results, etc.
- **Background unblock task** — A background `asyncio.Task` processes completed jobs and
  transitions blocked dependents to `ready`. This is deliberately not done inline for
  performance.

### Workers

Workers are Python processes that run `torcpy workflows run <id>`. Each worker:

1. Polls the server for `ready` jobs
2. Checks local resource availability (CPU, memory, GPU)
3. Claims a batch of jobs via `POST /workflows/{id}/jobs/claim`
4. Executes each job as an `asyncio.subprocess`
5. Reports results via `POST /workflows/{id}/results`
6. Completes the job via `POST /workflows/{id}/jobs/{job_id}/complete`

### CLI / Python Client

The `torcpy` command and `TorcClient` Python class are thin HTTP wrappers over the server API.
They share the same `httpx`-based async client.

## Data Flow

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Server
    participant Worker

    User->>CLI: torcpy run pipeline.yaml
    CLI->>Server: POST /workflows (create)
    CLI->>Server: POST /workflows/{id}/files (bulk)
    CLI->>Server: POST /workflows/{id}/jobs (bulk)
    CLI->>Server: POST /workflows/{id}/initialize
    Server->>Server: Build dependency graph
    Server->>Server: Mark ready jobs

    loop Poll until done
        Worker->>Server: POST /jobs/claim?count=5
        Server->>Worker: [job1, job2, ...]
        Worker->>Worker: Execute jobs in parallel
        Worker->>Server: POST /results (metrics)
        Worker->>Server: POST /jobs/{id}/complete?status=5
        Server->>Server: Background: unblock dependents
    end

    CLI->>User: Workflow finished
```

## Database Schema (Simplified)

```mermaid
erDiagram
    workflow ||--o{ job : contains
    workflow ||--o{ file : contains
    workflow ||--o{ user_data : contains
    workflow ||--o{ result : has
    job ||--o{ job_depends_on : "depends on"
    job ||--o{ job_input_file : reads
    job ||--o{ job_output_file : writes
    job }o--|| resource_requirements : uses
    job }o--|| failure_handler : uses
    job ||--o{ result : produces

    workflow {
        int id PK
        string name
        string user
        float timestamp
        json metadata
    }
    job {
        int id PK
        int workflow_id FK
        string name
        string command
        int status
        int priority
        int unblocking_processed
    }
    result {
        int id PK
        int job_id FK
        int return_code
        float exec_time_minutes
        int peak_memory_bytes
    }
```

## Next Steps

- [Job States](./job-states.md) — The full job lifecycle
- [Dependency Resolution](./dependencies.md) — How dependencies are built and resolved
