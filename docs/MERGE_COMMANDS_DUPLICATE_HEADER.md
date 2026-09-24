# The duplicated stanza header — diagnosis, and why the one-line fix is wrong

**Found by the operator reading r6's branch-site plan before applying it.**
Nothing was applied.

**FIXED — 2026-09-24.** The diagnosis below stands as written; §6 records what
shipped and the three further defects the fix surfaced. The duplicate was the
symptom; the rollback of a newly-created container was the finding.

```
"interface Loopback0",
"interface Loopback0",          <-- nobody authored this
" description branch site identity",
" ip address 10.255.1.16 255.255.255.255",
"exit",
"ip route 10.255.0.0 255.255.0.0 10.255.0.1"
```

`from_this_edit` lists the line once. The duplication is in the command
**builder**, not the attribution.

## 1. Where it comes from

`_section_chains()` yields `(line, ancestors)` with the ancestors **excluding
the line itself**, so a top-level header arrives with an empty chain. In
`merge_commands()`:

* `interface Loopback0` is in `to_add`, its chain is `[]`, `open_chain` is
  `[]` — equal, so nothing is extended — and the line is appended. **Copy one.**
* its first child arrives with chain `["interface Loopback0"]`, which differs
  from the still-empty `open_chain`, so the chain is extended into the
  program. **Copy two.**

The operator's hypothesis, confirmed: *a section header emitted once as the
stanza's opener and once as part of the stanza's own lines.*

**It fires for every brand-new stanza**, not just interfaces. Measured:

| intended | program |
|---|---|
| new `interface Loopback0` + 2 children | header twice |
| new `router ospf 1` + 2 children | header twice |
| new `router bgp` → `address-family` | **header twice, then `exit` and re-enter**, and the address-family line twice |
| new container with **no** children | correct — one copy, no `exit` |
| **existing** container, new child | correct — this is every case the fleet has deployed so far |

So every new stanza this tool has ever added carried it, and nothing noticed
because entering a stanza twice is idempotent on IOS.

## 2. Does a test assert the program has no duplicates?

**Yes — and it is pointed at a case that cannot produce one.**

`test_each_group_is_unwound_one_exit_per_level` asserts the **exact list**,
which would catch a duplicate outright. But `TestMergeCommands.RUNNING`
contains `interface GigabitEthernet0/1`, `interface GigabitEthernet0/2`,
`router bgp 65001` and ` address-family ipv4` — **every container already
exists on the device**, so no header is ever in `to_add` and the duplicating
branch is never reached.

This is worth stating precisely, because it changes what the repair is: the
assertions are **not** too weak. The fixture cannot fail them. A stronger
"no adjacent duplicates" assertion added to the same fixture would also
have passed. **What was missing was a fixture with a new container**, and
the natural one to write — "a sub-command gets its parent" — has the parent
present by construction.

## 3. Why the one-line fix is wrong, and this is the part that matters

Making the header open its own level (`open_chain = chain + [line]` when the
line is itself a container) removes the duplicate and immediately trips
`merge_commands()`'s own consistency assertion:

```
RuntimeError: merge_commands and program_structure disagree about which
lines are configuration: ['interface Loopback0']
```

That assertion exists because the forward and rollback paths once disagreed
about ancestry, and it is **right to fire**. It equates *"lines I set out to
add"* with *"leaves of the program"*, and that equation is **false whenever a
container is itself new**: `interface Loopback0` is simultaneously a line
being added and the ancestry of two other lines.

So the duplicate is load-bearing for the assertion. The obvious next thought
is that it is therefore load-bearing for rollback — **measured, and it is the
opposite.** With the duplicate, `program_structure` marks the first copy a
leaf and the second ancestry, and `rollback_commands()` produces:

```
no interface Loopback0        <-- removes it
interface Loopback0           <-- then re-creates it
 no description branch site identity
 no ip address 10.255.1.16 255.255.255.255
exit
```

**Self-cancelling.** It deletes the interface and immediately recreates it
empty. Deduplicated, rollback is coherent but incomplete:

```
interface Loopback0
 no description branch site identity
 no ip address 10.255.1.16 255.255.255.255
exit
```

— leaving an empty `interface Loopback0` the device never had.

**Neither is correct.** The right rollback for a container that did not exist
before is `no interface Loopback0` **alone**: the child negations are implied
by removing the container, and "rollback undoes what landed" means the device
returns to not having the interface at all.

So the duplicate was hiding a **pre-existing rollback defect** for
newly-created containers, and removing it without fixing that would swap a
self-cancelling program for a residue-leaving one — quieter, still wrong,
and no longer flagged by the assertion that currently fires.

## 4. What the fix has to do

1. **A newly-created container is both an added line and ancestry.** The
   forward/rollback consistency assertion has to express that rather than
   forbid it.
2. **Its rollback is the single negation of the container**, with the child
   negations suppressed as implied — bounded by
   `assert_rollback_provenance()` as every generated `no` already is.
3. **A fixture with a new container**, in `TestMergeCommands` and in the
   rollback tests. The exact-list assertion then earns its keep.
4. A **no-adjacent-duplicates** check over the program, with a floor so it
   cannot pass on an empty list.

## 5. Risk of applying r6's plan as it stands

Forward, the duplicate is harmless — IOS re-entering a stanza is idempotent,
and `assert_merge_only()` passes because the line does appear verbatim in the
intended config.

The exposure is **rollback only**, and rollback only runs if the push fails.
For r6 that is four lines onto a device with none of them, so a mid-push
failure is unlikely — but if it happened, the repair program would delete and
recreate the interface, which is not what anyone confirmed.


---

## 6. What shipped

`modules/nsot/deploy.py`, `modules/pipeline.py`,
`tests/test_new_container_programs.py`, and corrected expectations in
`test_deploy_safety.py` and `test_deploy_batch.py`. **3,195 passing**, five
negative controls each shown failing.

### 6.1 The duplicate

A line that is also a container now opens the level it names, so its children
do not re-emit it. r6's program is exactly what was authored:

```
interface Loopback0
 description branch site identity
 ip address 10.255.1.16 255.255.255.255
exit
ip route 10.255.0.0 255.255.0.0 10.255.0.1
```

### 6.2 The consistency assertion, restated rather than relaxed

It asserted *"the program's leaves are exactly the lines I set out to add"*.
That is false whenever a container is itself new. Split into the two
directions it was really guarding — **nothing intended was dropped**, and **no
leaf is configuration nobody asked for** — which is the half that stops a
synthesised line reaching a device.

### 6.3 Undoing a creation

`created_containers()` is the **one producer** of *"which sections did this
push bring into existence"*, consumed by the rollback builder and the
provenance guard, for the same reason `program_structure()` exists. A created
container's rollback is the single negation with its children implied:

```
no interface Loopback0
no ip route 10.255.0.0 255.255.0.0 10.255.0.1
```

### 6.4 Three further defects the fix surfaced

1. **The provenance guard refused the correct rollback.** It could not tell a
   section this push *created* from one it merely entered, so it rejected
   `no interface Loopback0` — and the pipeline silently dropped the device
   from the rollback set. `assert_rollback_provenance()` now takes
   `pre_config`. It is **optional, and that is not the bypassed-by-omission
   shape**: omitting it makes the guard *stricter*, and the rule about default
   fallbacks concerns arguments whose absence **loosens** a check.
2. **A created container must also have LANDED.** `landed_leaves()` sees
   leaves only, so without its own check a push rejected at its very first
   line would be "undone" by negating a section that was never created.
3. **An empty pre-change snapshot is not evidence the device had nothing.**
   Without a guard, every section looks created and the repair becomes `no` on
   all of them — the worst push this tool could produce, generated by the path
   meant to fix a failure.

### 6.5 The duplicate check was wrong on its first run

Two adjacent `exit` lines are correct unwinding — one per open level — and a
naive adjacent-equality check reported the two-level bgp case as a defect.
Caught by this file's own fixture, which is the argument for having one that
reaches two levels at all.

### 6.6 A test that pinned the defect as correct

`test_router_bgp_is_never_matched_against_router_ospf` had the **only** fixture
in the suite with a container absent from the pre-change config, and therefore
asserted the residue-leaving rollback — under a name about key matching. Its
own property is unchanged and still asserted; the expectation moved. Fourth
test in this project to pin a defect as correct.
