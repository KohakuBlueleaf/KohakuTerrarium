Output your plan as numbered steps. Each step should be:

1. Independently executable
2. Small enough to review in one pass
3. Clear about which files will be modified

Format:
```
Step 1: [action] - [files affected]
  Depends on: none
Step 2: [action] - [files affected]
  Depends on: Step 1
```

Mark dependencies between steps explicitly.
