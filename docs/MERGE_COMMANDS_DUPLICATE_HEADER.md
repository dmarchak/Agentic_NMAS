# The duplicated stanza header — diagnosis, and why the one-line fix is wrong

**Found by the operator reading r6's branch-site plan before applying it.**
Nothing was applied. **Nothing is fixed yet**, deliberately: the obvious fix
uncovers a larger defect it would hide.

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
