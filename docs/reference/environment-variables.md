# Environment Variables

## Client

| Variable | Default | Description |
|---|---|---|
| `TORCPY_API_URL` | `http://localhost:8080/torcpy/v1` | Server URL used by all CLI commands and `TorcClient()` |
| `USER` / `USERNAME` | (OS user) | Workflow owner when `user` is not set in spec |
| `CUDA_VISIBLE_DEVICES` | (unset) | Controls GPU detection by the resource tracker |

## Example: Connect to Remote Server

```bash
export TORCPY_API_URL=http://myserver.example.com:8080/torcpy/v1
torcpy workflows list
```

## Example: Restrict GPU Visibility

```bash
export CUDA_VISIBLE_DEVICES=0,1   # worker only sees GPUs 0 and 1
torcpy workflows run 42
```
