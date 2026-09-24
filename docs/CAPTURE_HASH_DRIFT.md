# `skipped_drifted` on r6 — what the guard actually compared

**Diagnosed from the code, 2026-09-24. Nothing changed yet.** The three
candidates offered are all ruled out by what the apply path does, and the
reason they were plausible is a docstring that names a source the code does
not use.

## The premise the docstrings create, and the code does not support

`apply()`'s docstring:

> *A device whose **fresh capture** no longer matches is skipped…*

`plan_batch()`'s:

> *`fresh_captures` maps device → the config read **at deploy time***

Neither is true on this path. Both `/deploy/plan` and `/deploy/apply` call
`_artifact_for()`, which calls `_captured_config(repo, hostname)` — a
deterministic read of **`config_repo/golden/<device>.cfg`**. `/deploy/apply`
then does:

```python
# Phase 3c reads a FRESH capture inside the pipeline (stage 4). Here the
# comparison is against the same captured artifact the plan used, so a
# change committed between plan and apply is caught before connecting.
fresh_captures[hostname] = captured
```

The comment is accurate and the variable name is not. **Nothing reads the
device between plan and apply**; the fresh read happens later, inside the
pipeline at stage 4, after this gate has already decided.

So:

| candidate | verdict |
|---|---|
| the self-signed certificate regenerating on r6 | **ruled out** — the device is not read here |
| something changed on r6 between plan and apply | **ruled out** — same |
| non-determinism in the capture (uptime, counters) | **ruled out** — `_captured_config()` is a file read |

Both sides are `sha256` of the same stored file. They can differ for exactly
one reason: **the golden config for r6 changed on disk between the plan and
the apply.**

## What to run

```bash
git -C data/lists/<slug>/config_repo log --oneline -- golden/r6.cfg
git -C data/lists/<slug>/config_repo diff HEAD~1 HEAD -- golden/r6.cfg
```

A commit timestamped between the two calls is the answer, and its diff is
what drifted. The skip entry also carries `fresh_capture` verbatim, so it can
be diffed against the file directly.

`save_golden()` is the only writer. A Save All is the likely candidate — it is
step 0d of the branch-site plan.

## The finding that stands whatever the diff says

**Two comparisons of "has this changed" disagree about what counts, and the
one on the deploy path is the strict one.** Measured on two configs differing
*only* in a regenerated self-signed certificate:

```
raw sha256 equal (the deploy guard)          : False
configs_equivalent (everything else)         : True
```

`_capture_hash()` is `sha256` of the raw text — no `strip_for_diff`, no
`strip_self_signed_certs()`. Every other "has this device changed" question in
the system goes through `configs_equivalent()`: the drift checker, restore
baselines, the freshness gate.

The consequence is one step removed from the original worry but the same
shape. It does not fire per deploy — but **a C8000v reboot followed by a Save
All writes a golden whose certificate bodies and `TP-self-signed-<chassis>`
name have changed**, and that invalidates every outstanding plan for that
device, for a difference the rest of the system has already decided is noise.
That is the drift checker's silencing waiting to happen on the deploy path: a
guard that fires on noise is a guard people learn to re-plan past without
reading, which turns the recompute-at-apply check into a formality.

## What the fix is, and why it is not applied yet

Hash the **normalised** capture — `strip_for_diff` plus
`strip_self_signed_certs()`, the same pipeline `configs_equivalent()` uses — so
the two comparisons agree on what a change is. Nothing that matters is
weakened: a difference that survives that normalisation is a difference in
configuration, which is exactly what the guard is for.

Held because the guard is mid-use and the first question is *what actually
changed*. Re-planning against a moved capture and applying immediately is how
a guard becomes a formality, and that applies to the person diagnosing it too.

## The smaller finding: the docstring cost the diagnosis

Three candidates were derived, all sound, all inapplicable — because two
docstrings and a variable name say *fresh capture* where the code re-reads a
stored file. Fourth instance in this project of confident prose beside correct
code (`manifest.py`'s slug example, `render_bootstrap`'s "what remains is what
makes the device reachable", `render_step`'s "from committed intent"). The
cost here is measurable: the entire first pass of the investigation was aimed
at the device.
