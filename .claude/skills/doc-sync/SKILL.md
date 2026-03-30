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
- An exposed class (dataclass, ABC, or public API) has fields added, removed, or renamed

## Checklist

After each code change (or any notebook/script), check each of the following:

| File | Update if... |
|---|---|
| `requirements.txt` | A new package is imported, or a version constraint changes |
| `README.md` | Visualizations produced (chart names, what they show), run instructions change, **or an exposed class has changed** |
| `CLAUDE.md` | The file's role, inputs, outputs, or public API changes |
| `.gitignore` | New output files are created that should not be committed |

## Exposed-class check (README.md)

When any of these are modified, audit `README.md` for stale references:

- **Event dataclasses** (`trading/events.py`): field names, types, or semantics in the "Event types" table
- **Params dataclasses** (`trading/base/strategy_params.py` or any `*Params` subclass): new or removed fields shown in code examples
- **ABCs** (`trading/base/`): method signatures or contracts described in the architecture section
- **Public API of `StrategyContainer`** (`add()`, `add_strategy()`): parameter changes reflected in the "Implementing a custom strategy" example

Scan README for every occurrence of the changed class or field name and update prose, tables, and code snippets to match.

## Quick Reference

1. Scan imports at the top of the modified file — any new packages?
2. Scan outputs (saved files, printed results) — do docs reflect the current outputs?
3. Check run instructions in README — are steps still accurate?
4. Check for new generated files — should they be gitignored?
5. Did any exposed class change? → audit README for stale field names, types, or code examples.
