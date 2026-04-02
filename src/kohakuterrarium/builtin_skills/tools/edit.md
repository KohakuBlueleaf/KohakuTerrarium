---
name: edit
description: Edit file via search/replace or unified diff (must read first)
category: builtin
tags: [file, io, edit, diff, patch]
---

# edit

Edit files using search/replace or unified diff. Supports two modes, auto-detected from arguments.

## SAFETY

- **You MUST read the file before editing it.** The tool will error if you haven't.
- If the file was modified since your last read, you must re-read it.
- Binary files cannot be edited.

## Mode 1: Search/Replace (recommended for simple changes)

Find an exact string and replace it.

### Arguments

| Arg | Type | Description |
|-----|------|-------------|
| path | @@arg | Path to file (required) |
| old_string | @@arg | Exact text to find (required) |
| new_string | @@arg | Replacement text (required) |
| replace_all | @@arg | Replace all occurrences (default: false) |

### Rules

- old_string must match the file content EXACTLY (including whitespace)
- If old_string appears multiple times and replace_all is false, provide more context to make it unique
- Set replace_all=true to replace every occurrence (useful for renaming)

### Example

```
tool call: edit(
  path: src/main.py
  old_string: def hello():
  new_string: def greet():
)
```

## Mode 2: Unified Diff (for multi-site or complex changes)

Apply standard unified diff patches.

### Arguments

| Arg | Type | Description |
|-----|------|-------------|
| path | @@arg | Path to file (required) |
| diff | body | Unified diff content (required) |

### Format

```
@@ -start,count +start,count @@
 context line (unchanged, starts with space)
-line to remove (starts with minus)
+line to add (starts with plus)
```

- `start` is 1-indexed line number
- `count` is the number of lines in that section
- Context lines must match the file exactly
- Multiple hunks can appear in one diff

### Example

```
tool call: edit(
  path: src/app.py
@@ -1,2 +1,3 @@
 import os
+import json
 import sys
@@ -20,2 +21,2 @@
-    return None
+    return {}
)
```

## Output Format

Search/replace:
```
Edited /path/to/file.py
  1 replacement(s) made
```

Unified diff:
```
Edited /path/to/file.py
  2 hunk(s) applied
  +3 -2 lines
```

## TIPS

- Use search/replace for single-site changes (simpler, less error-prone)
- Use unified diff for multi-site changes or when you need precise line control
- Always read the file first to see exact content and line numbers
