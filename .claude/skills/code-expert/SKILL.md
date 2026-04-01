---
name: code-expert
description: Use when writing, reviewing, or refactoring code — applies time/space complexity tradeoffs and audits for redundant variable declarations, duplicated definitions, and unnecessary loops before producing any solution.
---

# Code Expert

Senior-level code quality standard: every solution is chosen at the right point on the time/space tradeoff curve, and every implementation is stripped of dead weight before it ships.

## When to Use

- Writing a new function, class, or module
- Reviewing or refactoring existing code
- Choosing between algorithmic approaches
- Spotting redundancy, duplication, or bloat in a diff

## Part 1 — Complexity Tradeoff

Before writing code, state the tradeoff explicitly, then choose.

### Decision table

| Situation | Prefer |
|---|---|
| Called once / small input | Readable O(n²) over complex O(n log n) |
| Hot loop / large input | Optimal time even at memory cost |
| Memory is the constraint | Higher time complexity to avoid large aux structures |
| Both are equivalent | Simpler code wins unconditionally |

### Common upgrades worth making

| Naive pattern | Better | Why |
|---|---|---|
| Linear scan inside loop → O(n²) | Build lookup dict first → O(n) | Hash lookup is O(1) |
| Sorting to find min/max | `min()` / `max()` → O(n) | No need to fully sort |
| Repeated slicing `a[i:]` | Index pointer | Avoids O(n) copy each time |
| Recursive fib/dp without memo | Memo / bottom-up | Exponential → polynomial |
| Set membership via list | `set` / `dict` | O(n) → O(1) per lookup |

### Rule: state complexity before writing

```
# Time: O(n)  Space: O(1)
def find_max(values):
    ...
```

Always annotate non-trivial functions. If you can't state the complexity, you don't understand the algorithm yet.

## Part 2 — Simplicity Audit

Run this checklist on every diff before finalising.

### 1. Redundant variable declarations

A variable is redundant when it is assigned once and used exactly once with no clarifying purpose.

```python
# ❌ redundant
result = compute(x)
return result

# ✅ direct
return compute(x)
```

**Exception:** keep the variable when its name makes a complex expression readable, or when the value is used more than once.

### 2. Duplicated definitions

Same logic appearing in two or more places is a bug waiting to diverge.

```python
# ❌ duplicated threshold check
if value > 100:
    apply_cap(value)
...
if value > 100:
    log_cap(value)

# ✅ deduplicated
if value > 100:
    apply_cap(value)
    log_cap(value)
```

Duplication includes: copy-pasted constants, repeated guard clauses, identical comprehension bodies, and parallel `if/elif` chains that could be a loop over data.

### 3. Unnecessary loops

A loop is unnecessary when:
- A built-in does the same thing (`sum`, `any`, `all`, `map`, `zip`, `enumerate`)
- The loop body always executes exactly once
- The accumulation can be expressed as a comprehension without losing clarity

```python
# ❌ manual accumulation
total = 0
for x in values:
    total += x

# ✅ built-in
total = sum(values)

# ❌ loop that exits after one iteration
for item in collection:
    return item.value

# ✅ direct
return next(iter(collection)).value
```

**Exception:** keep a loop when the body has side effects or the built-in equivalent obscures intent.

## Audit workflow

```
Write solution
     │
     ▼
State complexity (time + space)
     │
     ▼
Is there a better tradeoff for this context? ──yes──▶ rewrite
     │ no
     ▼
Redundant variables? ──yes──▶ inline
     │ no
     ▼
Duplicated logic? ──yes──▶ consolidate
     │ no
     ▼
Unnecessary loops? ──yes──▶ replace with built-in or remove
     │ no
     ▼
Ship it
```

## Common mistakes

| Mistake | Fix |
|---|---|
| Optimising before profiling | State complexity first; optimise only when it matters |
| Inlining everything | Keep variables that name an intermediate concept |
| Over-deduplicating | Two things that look alike but evolve independently should stay separate |
| Replacing a clear loop with an unreadable one-liner | Clarity beats brevity |
