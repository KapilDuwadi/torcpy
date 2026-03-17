# REST API Reference

All endpoints are under the base path `/torcpy/v1`.

## Conventions

- **Request body**: JSON with `Content-Type: application/json`
- **Pagination**: All list endpoints accept `?offset=0&limit=10000` (max 10,000)
- **Response format**: JSON. Lists return `{"items": [...], "offset": 0, "limit": N, "has_more": false}`
- **Status codes**: `201` Created, `204` No Content, `404` Not Found, `422` Validation Error

---

## Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/ping` | Health check → `{"status": "ok"}` |
| `GET` | `/version` | Version info → `{"version": "0.1.0"}` |

---

## Workflows

| Method | Path | Description |
|---|---|---|
| `POST` | `/workflows` | Create workflow |
| `GET` | `/workflows` | List workflows |
| `GET` | `/workflows/{id}` | Get workflow |
| `PATCH` | `/workflows/{id}` | Update workflow |
| `DELETE` | `/workflows/{id}` | Delete workflow (cascades) |
| `POST` | `/workflows/{id}/cancel` | Cancel workflow |
| `POST` | `/workflows/{id}/initialize` | Build dependency graph |
| `POST` | `/workflows/{id}/reset` | Reset all jobs to uninitialized |
| `GET` | `/workflows/{id}/status` | Status summary with job counts |

---

## Jobs

| Method | Path | Description |
|---|---|---|
| `POST` | `/workflows/{wf_id}/jobs` | Create job |
| `GET` | `/workflows/{wf_id}/jobs` | List jobs (`?status=N` filter) |
| `GET` | `/workflows/{wf_id}/jobs/{id}` | Get job |
| `PATCH` | `/workflows/{wf_id}/jobs/{id}` | Update job |
| `DELETE` | `/workflows/{wf_id}/jobs/{id}` | Delete job |
| `POST` | `/workflows/{wf_id}/jobs/claim` | Claim next ready jobs (`?count=N&sort=...`) |
| `POST` | `/workflows/{wf_id}/jobs/{id}/complete` | Complete job (`?status=5`) |
| `POST` | `/workflows/{wf_id}/jobs/{id}/reset` | Reset job to uninitialized |

### `claim` Query Parameters

| Parameter | Default | Description |
|---|---|---|
| `count` | `1` | Number of jobs to claim (max 100) |
| `compute_node_id` | | Associate claimed jobs with a compute node |
| `sort` | `priority` | Sort method: `priority`, `gpus_runtime_memory`, `cpus_runtime_memory` |

### `complete` Query Parameters

| Parameter | Description |
|---|---|
| `status` | Terminal status code: 5 (completed), 6 (failed), 7 (canceled), 8 (terminated) |

---

## Files

| Method | Path | Description |
|---|---|---|
| `POST` | `/workflows/{wf_id}/files` | Create file |
| `GET` | `/workflows/{wf_id}/files` | List files |
| `GET` | `/workflows/{wf_id}/files/{id}` | Get file |
| `PATCH` | `/workflows/{wf_id}/files/{id}` | Update file |
| `DELETE` | `/workflows/{wf_id}/files/{id}` | Delete file |

---

## User Data

| Method | Path | Description |
|---|---|---|
| `POST` | `/workflows/{wf_id}/user_data` | Create user data item |
| `GET` | `/workflows/{wf_id}/user_data` | List user data |
| `GET` | `/workflows/{wf_id}/user_data/{id}` | Get user data item |
| `PATCH` | `/workflows/{wf_id}/user_data/{id}` | Update user data |
| `DELETE` | `/workflows/{wf_id}/user_data/{id}` | Delete user data |

---

## Resource Requirements

| Method | Path | Description |
|---|---|---|
| `POST` | `/workflows/{wf_id}/resource_requirements` | Create |
| `GET` | `/workflows/{wf_id}/resource_requirements` | List |
| `GET` | `/workflows/{wf_id}/resource_requirements/{id}` | Get |
| `PATCH` | `/workflows/{wf_id}/resource_requirements/{id}` | Update |
| `DELETE` | `/workflows/{wf_id}/resource_requirements/{id}` | Delete |

---

## Results

| Method | Path | Description |
|---|---|---|
| `POST` | `/workflows/{wf_id}/results` | Record execution result |
| `GET` | `/workflows/{wf_id}/results` | List results (`?job_id=N` filter) |
| `GET` | `/workflows/{wf_id}/results/{id}` | Get result |
| `DELETE` | `/workflows/{wf_id}/results/{id}` | Delete result |

---

## Compute Nodes

| Method | Path | Description |
|---|---|---|
| `POST` | `/workflows/{wf_id}/compute_nodes` | Register compute node |
| `GET` | `/workflows/{wf_id}/compute_nodes` | List compute nodes |
| `GET` | `/workflows/{wf_id}/compute_nodes/{id}` | Get compute node |
| `PATCH` | `/workflows/{wf_id}/compute_nodes/{id}` | Update (e.g., deactivate) |
| `DELETE` | `/workflows/{wf_id}/compute_nodes/{id}` | Delete |

---

## Events

| Method | Path | Description |
|---|---|---|
| `POST` | `/workflows/{wf_id}/events` | Create event |
| `GET` | `/workflows/{wf_id}/events` | List events (newest first) |
| `GET` | `/workflows/{wf_id}/events/{id}` | Get event |
| `DELETE` | `/workflows/{wf_id}/events/{id}` | Delete event |

---

## Failure Handlers

| Method | Path | Description |
|---|---|---|
| `POST` | `/workflows/{wf_id}/failure_handlers` | Create handler |
| `GET` | `/workflows/{wf_id}/failure_handlers` | List handlers |
| `GET` | `/workflows/{wf_id}/failure_handlers/{id}` | Get handler |
| `DELETE` | `/workflows/{wf_id}/failure_handlers/{id}` | Delete handler |

---

## Schedulers

| Method | Path | Description |
|---|---|---|
| `POST` | `/workflows/{wf_id}/local_schedulers` | Create local scheduler |
| `GET` | `/workflows/{wf_id}/local_schedulers` | List |
| `GET` | `/workflows/{wf_id}/local_schedulers/{id}` | Get |
| `DELETE` | `/workflows/{wf_id}/local_schedulers/{id}` | Delete |
| `POST` | `/workflows/{wf_id}/slurm_schedulers` | Create Slurm scheduler |
| `GET` | `/workflows/{wf_id}/slurm_schedulers` | List |
| `GET` | `/workflows/{wf_id}/slurm_schedulers/{id}` | Get |
| `DELETE` | `/workflows/{wf_id}/slurm_schedulers/{id}` | Delete |
