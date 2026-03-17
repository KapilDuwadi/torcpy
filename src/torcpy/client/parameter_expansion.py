"""Parameter expansion for workflow specs.

Supports:
  - Integer ranges: "1:100", "0:100:10"
  - Float ranges: "0.0:1.0:0.1"
  - Lists: "[1,5,10]", "['train','test','validation']"
  - Format specifiers: {param:03d}, {param:.4f}
  - Cartesian product (default) and zip combination modes
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from itertools import product
from typing import Any


@dataclass
class ParameterValue:
    name: str
    values: list[Any]

    @classmethod
    def parse(cls, name: str, spec: str) -> ParameterValue:
        """Parse a parameter specification string into concrete values."""
        spec = spec.strip()

        # List format: [1,2,3] or ['a','b','c']
        if spec.startswith("[") and spec.endswith("]"):
            try:
                values = ast.literal_eval(spec)
            except (ValueError, SyntaxError):
                # Try comma split
                inner = spec[1:-1]
                values = [v.strip().strip("'\"") for v in inner.split(",")]
            return cls(name=name, values=list(values))

        # Range format: start:end or start:end:step
        parts = spec.split(":")
        if len(parts) in (2, 3):
            try:
                # Try float range
                if any("." in p for p in parts):
                    start = float(parts[0])
                    end = float(parts[1])
                    step = float(parts[2]) if len(parts) == 3 else 1.0
                    values = []
                    current = start
                    while current <= end + step * 0.001:  # epsilon for float precision
                        values.append(current)
                        current += step
                    return cls(name=name, values=values)
                else:
                    start = int(parts[0])
                    end = int(parts[1])
                    step = int(parts[2]) if len(parts) == 3 else 1
                    return cls(name=name, values=list(range(start, end + 1, step)))
            except ValueError:
                pass

        # Single value
        try:
            return cls(name=name, values=[int(spec)])
        except ValueError:
            try:
                return cls(name=name, values=[float(spec)])
            except ValueError:
                return cls(name=name, values=[spec])


def substitute_template(template: str, params: dict[str, Any]) -> str:
    """Substitute {param} and {param:format} placeholders in a string."""

    def _replace(match: re.Match) -> str:  # type: ignore[type-arg]
        name = match.group(1)
        fmt = match.group(2)
        if name not in params:
            return match.group(0)  # leave unmatched
        value = params[name]
        if fmt:
            return format(value, fmt)
        return str(value)

    return re.sub(r"\{(\w+)(?::([^}]+))?\}", _replace, template)


def expand_parameters(
    parameters: dict[str, str],
    mode: str = "cartesian",
) -> list[dict[str, Any]]:
    """Expand parameter specs into a list of concrete parameter dictionaries.

    Args:
        parameters: Mapping of param name -> spec string
        mode: "cartesian" for Cartesian product, "zip" for zip combination

    Returns:
        List of dicts, each mapping param name -> concrete value
    """
    if not parameters:
        return [{}]

    parsed = [ParameterValue.parse(name, spec) for name, spec in parameters.items()]
    names = [p.name for p in parsed]
    value_lists = [p.values for p in parsed]

    if mode == "zip":
        min_len = min(len(v) for v in value_lists)
        return [
            dict(zip(names, vals))
            for vals in zip(*(v[:min_len] for v in value_lists))
        ]
    else:  # cartesian
        return [dict(zip(names, combo)) for combo in product(*value_lists)]
