---
name: python
description: Execute Python code in a subprocess
category: builtin
tags: [code, execution, interpreter]
---

# python

Execute Python code in a subprocess and return output.

## WHEN TO USE

- Quick computations or data transformations
- Testing code snippets
- Checking Python environment/packages
- Complex string/data processing

## HOW TO USE

```
##tool##
name: python
args:
  code: |
    <python code>
##tool##
```

## Arguments

| Arg | Required | Description |
|-----|----------|-------------|
| `code` | Yes | Python code to execute |

## Examples

```yaml
# Simple computation
##tool##
name: python
args:
  code: |
    result = sum(range(100))
    print(f"Sum: {result}")
##tool##

# Check packages
##tool##
name: python
args:
  code: |
    import sys
    print(f"Python {sys.version}")
##tool##

# Data processing
##tool##
name: python
args:
  code: |
    import json
    data = {"name": "test", "values": [1, 2, 3]}
    print(json.dumps(data, indent=2))
##tool##
```

## LIMITATIONS

- Runs in isolated subprocess (no state persistence)
- Timeout applies (default: 30 seconds)
- Only packages installed in environment are available

## TIPS

- Use `print()` to output results
- For file operations, prefer `read`/`write` tools
- Check package availability before using
