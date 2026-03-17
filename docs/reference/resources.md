# Resource Formats Reference

## Memory Strings

| Suffix | Multiplier | Example | Bytes |
|---|---|---|---|
| (none) | × 1 | `"1024"` | 1,024 |
| `k` / `K` | × 1,024 | `"512k"` | 524,288 |
| `m` / `M` | × 1,024² | `"4m"` | 4,194,304 |
| `g` / `G` | × 1,024³ | `"16g"` | 17,179,869,184 |
| `t` / `T` | × 1,024⁴ | `"2t"` | 2,199,023,255,552 |

The `b` suffix is ignored (`"4gb"` = `"4g"`). Case-insensitive.

## Runtime / Duration (ISO 8601)

Format: `P[nD]T[nH][nM][nS]`

| Value | Duration |
|---|---|
| `"PT30S"` | 30 seconds |
| `"PT5M"` | 5 minutes |
| `"PT30M"` | 30 minutes |
| `"PT2H"` | 2 hours |
| `"PT1H30M"` | 1 hour 30 minutes |
| `"P1D"` | 1 day |
| `"P1DT12H"` | 1 day 12 hours |

The `T` separator is required when specifying time components.

## Resource Requirements Fields

| Field | Type | Unit | Example |
|---|---|---|---|
| `num_cpus` | int | CPU cores | `4` |
| `num_gpus` | int | GPU devices | `1` |
| `num_nodes` | int | Compute nodes | `1` |
| `memory` | string | — | `"16g"` |
| `runtime` | string | ISO 8601 | `"PT4H"` |
