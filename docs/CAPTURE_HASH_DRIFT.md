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


---

## 7. The golden had not changed either — so the seam was measured

The operator then ruled out the remaining candidate: `golden/r6.cfg` was last
touched at 05:45:37 by the rotation commit, nothing since, and its
`sha256[:16]` is **`c29fa63582da8f57` — exactly the `capture_hash` the plan
reported.** So both calls read the same bytes and the apply still skipped.

That leaves the comparison itself, and the hypothesis worth testing was that
the two sides were never going to be equal — a guard that refuses **every**
deploy, whose only possible outcome is `skipped_drifted`, unnoticed because
the one thing that would notice is a deploy that completes.

**Measured, and it is not that.** Driving `/deploy/plan` into `/deploy/apply`
through the Flask test client, with `_artifact_for` returning the same capture
on both calls:

```
PLAN   capture_hash : <sha256(CAPTURE)[:16]>
APPLY  deployed     : ["r6"]
```

The handshake works. `plan_batch` keys on `artifact.device`, `_artifact_for`
passes the hostname to `build_artifact`, and `fresh_captures` and
`confirmations` are both keyed by hostname — all consistent, and now asserted
rather than inspected (`tests/test_deploy_plan_apply_seam.py`, seven tests,
two negative controls).

### What that leaves, and the one command that settles it

Something differed between the two **live** calls that the stub removes. The
skip entry carries `fresh_capture` verbatim, so:

```bash
python3 - <<'EOF'
import hashlib, json
fresh = json.load(open("apply-response.json"))["...skipped entry..."]["fresh_capture"]
print(hashlib.sha256(fresh.encode()).hexdigest()[:16])
EOF
```

* **equals `c29fa63582da8f57`** → the capture was identical and the
  *confirmation value that arrived* was not it. The wizard reads
  `d.capture_hash` into `data-hash` and sends `b.dataset.hash`; a hand-built
  request is the other possibility.
* **differs** → `_captured_config()` returned different bytes at apply time.
  Diff `fresh_capture` against the file and the difference is the answer.

One command, and it partitions the space — the discriminator rule, applied to
a diagnosis that has now produced two wrong hypotheses (mine: the golden
changed; the operator's: the guard never matches). **Both were sound from what
we had and both were reasoning where a measurement was one command away.**

## 8. A separate gap the seam test found

`/deploy/apply` recomputes the command fingerprint and compares it **only when
`command_hashes` is supplied**:

```python
expected = command_hashes.get(hostname)
if expected is not None:
    ...
```

The deploy wizard sends `JSON.stringify({confirmations})` — **and nothing
else.** So from the only client that reaches this route, the recompute-and-
compare **never runs**, and *"the list is recomputed at apply and compared
against the confirmed fingerprint"* — the deploy path's central claim — is not
exercised. The restore path (`partials__golden_repo.3.js`) does send
`command_hashes`, which is the positive anchor: the payload is buildable and
one client builds it.

Pinned rather than fixed, because changing what the wizard sends changes
deploy behaviour and the guard is mid-diagnosis. The test asserts the gap and
says what it should become.


---

## 9. Resolved: the guard was right and could not say so

All three measured identical — `fresh_capture`, the plan's `capture_hash`, and
the file on disk, all `c29fa63582da8f57` — and the guard still refused.

That is **arithmetic, not a hypothesis**. `fresh_hash` is
`sha256(fresh)[:16]`, and `fresh` is what the entry publishes as
`fresh_capture`. If that hashes to `c29fa63582da8f57` and
`fresh_hash != confirmed[device]` fired, then **`confirmed["r6"]` was not
`c29fa63582da8f57`**. The value that arrived in the request was something
else — a wrong field, a copied value carrying whitespace, a stale plan. A
trailing newline alone reproduces it exactly.

### The two questions asked directly

1. **Does anything else produce `skipped_drifted`?** No — **one** producer,
   `deploy.py:1222`. The outcome is not reused, so the reason text is attached
   to the only condition that raises it.
2. **Could a stale `command_hash` surface here?** No. The recompute branch in
   `/deploy/apply` produces `outcome: "refused"` with its own reason and
   `continue`s, so the device never reaches `plan_batch`. Since the report said
   `skipped_drifted`, **the command fingerprint was accepted** —
   `2c6d960d0990f2bf` was current, and the command hash is not the problem.

### The defect, which is the reporting

The entry carried `device`, `outcome`, `reason` and **`fresh_capture`** — an
entire device configuration — and **neither operand**. A guard that refuses on
a comparison and then does not say what it compared turned a one-line question
into four rounds and three wrong hypotheses (the golden changed; the guard
never matches; a stale command hash). Every one of them would have ended with
two sixteen-character strings printed side by side.

Fixed: `confirmed_hash` and `current_hash` are in the entry **and in the
sentence**, and the reason states the comparison and offers the device having
changed as a *possibility* rather than asserting it. The `refused` entry a
hundred lines above already had this shape — which is the anchor: one branch
of the same function got it right.

```
the capture you confirmed against is not the capture being deployed:
confirmed '2c6d960d0990f2bf', read 'e4fa07ef244a9f97'. The device may have
changed, or the confirmed value may not be this capture's hash — re-preview
to see what it looks like now
```

`tests/test_deploy_plan_apply_seam.py`, fourteen tests, four negative controls.
