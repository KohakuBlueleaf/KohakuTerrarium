---
name: multi_edit
description: Apply multiple search/replace edits to one file atomically (path, edits). Use info(multi_edit) first.
category: builtin
tags: [file, io, edit, batch, refactor]
---

# multi_edit

Apply an ordered list of search/replace edits to a single file in one atomic
operation. All edits succeed or none do.

## SAFETY

- **You MUST read the file before editing it.** The tool will error if you haven't.
- If the file was modified since your last read, you must re-read it.
- Binary files cannot be edited.
- All edits are applied in memory first; the file on disk is written back only
  after every edit succeeds. On any failure the file is left untouched.

## When to use

- Renaming a symbol across multiple call sites in the same file.
- Coordinated multi-site refactors where partial application would leave the
  file broken.
- Any time you would otherwise call `edit` two or more times on the same file.

For a single edit, prefer `edit` — it has a simpler interface.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| path | @@arg | Path to file (required) |
| edits | @@arg | Ordered list of `{old, new, replace_all?}` objects (required) |

### Per-edit fields

| Field | Type | Description |
|-------|------|-------------|
| old | string | Exact text to find (required, non-empty) |
| new | string | Replacement text (required, may be empty) |
| replace_all | bool | Replace every occurrence in this step (default: false) |

## Semantics

- Edits are applied **sequentially**: edit N sees the file as modified by
  edits 0..N-1. Write each `old` to match the state *after* the previous edits.
- If `old` appears more than once and `replace_all` is false, that edit fails
  (same rule as the `edit` tool). Add more context or set `replace_all: true`.
- If any edit fails, the whole call fails and the file is not written.

## Example

```
tool call: multi_edit(
  path: src/foo.py
  edits: [
    {"old": "class OldName", "new": "class NewName"},
    {"old": "OldName(", "new": "NewName(", "replace_all": true},
    {"old": "# TODO: rename", "new": ""}
  ]
)
```

## Output

Success:

```
Edited /abs/path/src/foo.py
  3/3 edits applied
  replacements: 1, 7, 1
```

Failure (file unchanged):

```
multi_edit failed: edit[2] did not apply (file unchanged)
  edit[0] ok: 1 replacement(s)
  edit[1] ok: 7 replacement(s)
  edit[2] ERROR: 'old' not found in file after prior edits. ...
```

## TIPS

- Order matters. If edit A changes the text that edit B's `old` depends on,
  put A after B or update B's `old` to match the post-A state.
- For independent non-overlapping edits, any order works — but keep them in
  top-to-bottom file order for readability.
- If you find yourself repeating the same `old`/`new` with `replace_all: false`
  over and over, you probably want a single edit with `replace_all: true`.
