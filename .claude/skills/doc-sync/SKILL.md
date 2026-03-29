---
name: doc-sync
description: Use when a notebook, script, or source file is modified — checks whether requirements.txt, README.md, CLAUDE.md, or .gitignore need updating to reflect the change.
---

# doc-sync

## Overview

After modifying a file that affects dependencies, outputs, or project structure, check and update downstream documentation files so they stay accurate.

## When to Use

- A Jupyter notebook is modified (new imports, new charts, changed outputs)
- A script gains or removes a dependency
- New files are generated

## Checklist

After each code change (or any notebook/script), check each of the following:

| File | Update if... |
|---|---|
| `requirements.txt` | A new package is imported, or a version constraint changes |
| `README.md` | Visualizations produced (chart names, what they show) or run instructions change |
| `CLAUDE.md` | The file's role, inputs, or outputs change |
| `.gitignore` | New output files are created that should not be committed |

## Quick Reference

1. Scan imports at the top of the modified file — any new packages?
2. Scan outputs (saved files, printed results) — do docs reflect the current outputs?
3. Check run instructions in README — are steps still accurate?
4. Check for new generated files — should they be gitignored?
