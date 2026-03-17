# Parameter Syntax Reference

## Parameter Formats

| Format | Example | Values Produced |
|---|---|---|
| Integer range | `"1:5"` | `1, 2, 3, 4, 5` |
| Integer range with step | `"0:10:2"` | `0, 2, 4, 6, 8, 10` |
| Float range | `"0.0:1.0:0.25"` | `0.0, 0.25, 0.5, 0.75, 1.0` |
| Integer list | `"[1, 5, 10, 50]"` | `1, 5, 10, 50` |
| Float list | `"[0.001, 0.01, 0.1]"` | `0.001, 0.01, 0.1` |
| String list | `"[train, test, val]"` | `train, test, val` |
| Single value | `"42"` | `42` |

## Template Substitution

Use `{param}` or `{param:format}` in any string field: `name`, `command`, `path`, `depends_on`.

### Format Specifiers

| Template | Input | Output |
|---|---|---|
| `{i}` | `42` | `42` |
| `{i:03d}` | `5` | `005` |
| `{i:05d}` | `42` | `00042` |
| `{lr:.4f}` | `0.001` | `0.0010` |
| `{lr:.2f}` | `0.1` | `0.10` |
| `{lr:.2e}` | `0.001` | `1.00e-03` |
| `{name}` | `train` | `train` |

All standard Python format specifiers are supported.

## Expansion Modes

### `cartesian` (default)

Produces all combinations (Cartesian product):

```yaml
parameters:
  lr: "[0.001, 0.01]"
  bs: "[32, 64]"
parameter_mode: cartesian
```

Produces 4 combinations: `(0.001,32)`, `(0.001,64)`, `(0.01,32)`, `(0.01,64)`.

### `zip`

Pairs parameters positionally (like Python's `zip`):

```yaml
parameters:
  dataset: "[train, val, test]"
  model: "[small, medium, large]"
parameter_mode: zip
```

Produces 3 pairs: `(train,small)`, `(val,medium)`, `(test,large)`.

Number of results = length of the shortest parameter list.

## Regex Dependencies

After expansion, `depends_on_regexes` matches against all expanded job names:

```yaml
jobs:
  - name: train_{i}
    parameters:
      i: "1:10"

  - name: aggregate
    depends_on_regexes:
      - "train_\\d+"   # matches train_1 through train_10
```

Regexes are matched with `re.match()` (anchored at start). Use `.*` to match the full name.
