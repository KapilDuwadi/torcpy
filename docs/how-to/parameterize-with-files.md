# How-To: Parameterize Jobs with Files

When each parameterized job reads/writes a unique file, use template substitution in both
the job and file specs to create matching pairs.

## Pattern

```yaml
files:
  - name: output_{i:03d}
    path: results/output_{i:03d}.csv
    parameters:
      i: "1:10"

jobs:
  - name: process_{i:03d}
    command: python process.py --id {i} --output results/output_{i:03d}.csv
    parameters:
      i: "1:10"
    output_files: [output_{i:03d}]   # template matched to file name
```

TorcPy expands both specs with the same parameters, producing pairs:
- `process_001` → writes `output_001`
- `process_002` → writes `output_002`
- ...

## Full Example: Data Shards

```yaml title="shards.yaml"
name: shard-processing

files:
  - name: shard_{i:03d}_input
    path: data/shards/shard_{i:03d}.parquet
    st_mtime: 1710000000.0   # pre-existing inputs
    parameters:
      i: "1:50"

  - name: shard_{i:03d}_output
    path: results/shards/shard_{i:03d}_processed.parquet
    parameters:
      i: "1:50"

  - name: final_dataset
    path: results/final.parquet

jobs:
  - name: process_shard_{i:03d}
    command: >
      python process_shard.py
        --input data/shards/shard_{i:03d}.parquet
        --output results/shards/shard_{i:03d}_processed.parquet
    parameters:
      i: "1:50"
    input_files: [shard_{i:03d}_input]
    output_files: [shard_{i:03d}_output]
    resource_requirements:
      num_cpus: 2
      memory: "4g"
      runtime: "PT30M"

  - name: merge
    command: python merge_shards.py --input-dir results/shards/ --output results/final.parquet
    depends_on_regexes:
      - "process_shard_.*"
    output_files: [final_dataset]
```

## Key Points

- File `name` and job `output_files`/`input_files` references must use **identical templates**
  with the same parameter names and format specifiers.
- The `st_mtime` field on input shards marks them as pre-existing (no job produces them).
- Implicit dependencies flow from file relationships — `merge` has no explicit `depends_on`,
  but TorcPy inserts dependencies because it reads output files of the processing jobs.
