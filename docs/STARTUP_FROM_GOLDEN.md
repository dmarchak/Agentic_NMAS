# Oxidized, goldens, and what a redeploy bakes in — corrected assessment

**§3 and §4 are BUILT** (2026-09-24). The read client, the sanitiser's
pre-write gate, the authorisation path and the Monitoring signal all ship;
§8 below records what measuring them changed. §0–2 stand as written.

**The migration in §0 was never built, and should not be.** The first version
of this document proposed sourcing startup files from goldens instead of
Oxidized. **That was wrong, and the sanitizer's own header says why** —
recorded here rather than deleted, because the mistake is the useful part.

## 0. The correction

A golden **cannot** replace Oxidized as the source, because the sanitizer is
not cleaning up Oxidized's quirks. It compensates for two facts about
**running configs in general**:

1. **`no shutdown` re-injection.** A running config records `shutdown` on a
   down interface and **nothing at all** on an up one. So any harvested
   config brings every addressed interface back admin-down. That cost a full
   rebuild on 2026-08-30.
2. **`crypto key generate rsa` re-issued for switches.** The RSA key is not
   in a running config either.

**A golden is a captured running config, so it has both blind spots
identically.** The sanitizer exists because *a running config is not a
startup config* — and swapping the source changes only **which capture gets
sanitised**.

### What the risk actually is

Not *"Oxidized is the wrong store"*. It is:

> **Oxidized's copy may be newer than the approved one**, so a redeploy can
> bake in a change nobody approved.

**A freshness question, not a source question.** That reframing is the
finding, and it makes the work a **comparison rather than a migration** —
much smaller, and it leaves the sanitizer's two compensations exactly where
they belong.

### Why I got it wrong, since the shape recurs

I reasoned from *"the source of truth should be the source"* — a principle
this project does hold — without reading the thing that would have said it
does not apply here. The sanitizer's header states both compensations
outright. **Three lines of grep is not a reading**, which I had already said
one turn earlier and then produced a full assessment anyway.

The tell was available: an assessment whose central claim is about a script,
built entirely from artefacts in a different repository. That is the same
*"every piece of evidence comes from one artifact and the conclusion is
about another"* pattern recorded in Stage 2.

---

## 1. Can a golden be replayed as a startup-config?

**No, and the first line is why.**

`repo.py:263` writes every golden with one header:

```python
return f"! Golden config — {hostname} ({mgmt_ip})\n{body}\n"
```

Measured: that em dash is **U+2014, three UTF-8 bytes at column 17**, and
this project's own guard refuses it:

```
deploy.assert_sendable() → REFUSED — '—' (U+2014) at column 1.
                            The IOS CLI accepts printable ASCII only.
```

**And the failure it predicts is already recorded.** From `CLAUDE.md`:

> the same character later hung a vIOS boot from a **comment** in a startup
> config, because vrnetlab types that file into the console line by line and
> waits for a prompt after each one. The C8000v booted the identical
> content, since it loads its startup config as a file — **so one platform
> can never reveal the property.**

s1–s4 are vIOS. **A golden replayed as-is would hang the boot of exactly the
four devices whose startup files already bit once**, while r1–r5 booted it
fine and told you nothing.

So the goldens need the same treatment. Which makes the answer to the third
question mostly *yes* — the change is the source — but not entirely, and §3
says where the difference is.

## 2. What the sanitizer does that a golden also needs

All three jobs already have counterparts in `modules/nsot/normalize.py`,
built for other consumers:

| the sanitizer's job | what exists | fit |
|---|---|---|
| header stripping | `strip_nmas_header()`, `has_nmas_header()` | **yes** — measured, removes exactly the header line above |
| ASCII validation | `find_non_printable()`, `describe_non_printable()`; `deploy.assert_sendable()` is the refusal | **yes**, and it is *required*, not optional |
| truncation guard | `push_safe_lines()` | **NO — wrong consumer** |

**`push_safe_lines()` is the wrong filter here, measured:** it drops `end`
*and* bare `!`. A startup config needs `end`. `CLAUDE.md` already says why —
the filters are *"not one list — four different jobs"*, and
`push_safe_lines()` filtering `end` is *"a truncation guard, not cleanup"*,
correct for a **config-mode push** and wrong for a file the device reads at
boot.

`strip_for_repo()` keeps `end`, but it is the repo-write filter, not this.

**So a startup config is a fifth job**, and reaching for the nearest
existing filter would truncate the file at exactly the line that ends it.
What is needed is one small producer — strip the NMAS header, keep `end` and
structure, assert printable over the **whole** text, and **refuse rather
than silently fix**, because a config that was quietly repaired is a config
nobody reviewed.

One platform rule comes with it: on console-replayed platforms the file
should carry **no prose comments at all**, which `bootstrap_config` already
does for the same reason.

## 3. The thing to build: the freshness comparison

### It is a CONTENT comparison, reported with time as context

*"Newer"* on its own fires constantly and means nothing — Oxidized polls, so
its copy is newer than the golden most of the time, including immediately
after an approved save.

**The finding is that the content differs.** The timestamp then says which
way, and that is what makes it actionable:

| content | Oxidized time vs golden | reading |
|---|---|---|
| same | any | nothing to report — the normal case |
| differs | Oxidized **newer** | **a change nobody approved**, and a redeploy would bake it in |
| differs | golden newer | the approved state has moved and Oxidized has not polled yet — a race, not a finding |

Comparing content needs normalising, and the comparator already exists:
`roundtrip.configs_equivalent()` is section-aware over `strip_for_diff`, so
bare `!` and ordering cannot decide it. That is the same function a restore
baseline is measured with, which is the right precedent — both are asking
*"is this device's state the approved one"*.

### Cost

One API call per device against Oxidized's own index, versus an SSH session.
`modules/integrations/oxidized.py` has `test_connection()` and `monitor()`
and **no config fetch**, so a read client method is the new code. That is
Phase 5's shape and the cheapest drift source in the stack.

## 4. Where it belongs: both, and they are not the same check

**Both, and the distinction is worth keeping** — they answer different
questions and have different failure modes.

### The sanitizer's pre-write gate

**The one that matters**, because it is the last moment before an unapproved
state becomes **durable**. Per device, before writing a startup file:
refuse, name the device, and say what differs.

A redeploy is when this is load-bearing, and a gate that runs only at sync
time tells you at the worst possible moment — which is an argument for the
signal below, not against the gate.

**It needs an explicit authorisation path, or it will be bypassed.** The
legitimate case is real: someone made an approved change and the golden has
not been saved yet. A gate with no way through teaches operators to disable
it, which is how the drift checker came to be switched off for 24 days.
`authorise_retry()` is the precedent — an explicit, recorded action, not a
flag.

### The Monitoring signal

Answers *"is the fleet diverging"* **continuously and cheaply**, without
waiting for a sync run. It is a **report**, not a gate: it cannot refuse
anything, and it should not try.

Its value is timing. The gate discovers divergence when somebody is already
preparing a redeploy; the signal discovers it when it happens, which is when
the person who caused it still remembers what they did.

### Why not one of them

* **Gate only** — divergence is invisible until a sync, and the first
  report arrives at the least convenient moment.
* **Signal only** — nothing stops an unapproved state being written to a
  startup file. The signal would have shown the s1/s2 VLAN loss *and* the
  redeploy would still have persisted it.

They are the same measurement consumed at two moments, which is why one
comparator serves both.

## 5. What this does to the three scoped sync changes

**All three survive unchanged**, because the source is not moving:

| change | after |
|---|---|
| **1. per-device destination** | unchanged |
| **2. platform column** | **unchanged, and still for the original reason** — the sanitizer's router/switch split is real work (`no shutdown` re-injection and `crypto key generate rsa` differ by kind), not an artefact of Oxidized. My previous claim that the decision "moves into the NMAS" was downstream of the wrong premise |
| **3. ask the map, stop on exit 2** | unchanged |
| **`--reconcile`** | unchanged — the sanitizer's output really is the population, because the sanitizer really is the producer |

**And grouping is `--files-from`**, settled by reading rather than by the
criterion I offered: `./configs` holds exactly one `<hostname>.cfg` per
device and nothing else, and the script **already stages** — rsync to
`/tmp/oxidized-staged` on the clab host, diff there, `cp $STAGE/*.cfg
$REMOTE_DIR/` on confirm. Per-lab grouping is splitting that one `cp` by
destination. Small.

The staging directory also gives `--stray` a second place to earn its keep:
run it against `/tmp/oxidized-staged` before the `cp`, and litter is caught
before it is durable rather than after.

## 6. What survives from the wrong version

Two measurements, still true and still useful, now for a smaller purpose:

* **A golden carries a non-ASCII header** (`! Golden config — …`, U+2014),
  and `deploy.assert_sendable()` refuses it. Anything that ever replays a
  golden into a console — a restore, a rebuild, a future bootstrap from a
  capture — must strip it first. `strip_nmas_header()` does.
* **`push_safe_lines()` is the wrong filter for a startup file**: measured,
  it drops `end` and bare `!`. It is a truncation guard for a config-mode
  push. Reaching for the nearest existing filter would truncate a startup
  file at exactly the line that ends it.

Both are pinned in `test_startup_safety_composite.py` so they do not need
re-deriving, whichever consumer meets them next.

## 7. Still unmeasured

**Certificate bodies.** r1–r5 goldens each carry three
`crypto pki certificate chain` / `certificate self-signed` lines. Whether a
self-signed certificate body replays into a startup config is unmeasured —
the device regenerates its own key material on boot, and a stale body may be
ignored, rejected, or collide.

Less urgent now that the source is not moving, since the sanitizer already
handles whatever it handles today. But it is the **same class** as the two
compensations above — *a running config is not a startup config* — and if
there is a third blind spot, that is where it is.


---

## 8. What was built, and the three things measuring it changed

| part | where |
|---|---|
| read client | `OxidizedIntegration.fetch_config()`, `.node_times()` |
| comparator | `modules/nsot/freshness.py` |
| gate | `POST /freshness/gate`, called by `scripts/nmas-oxidized-freshness` from the sanitiser before it writes |
| authorisation | `POST /freshness/authorise` — a person, a reason, one divergence |
| signal | `GET /freshness/report` + `templates/partials/freshness_signal.html` |
| pinned | `tests/test_oxidized_freshness.py` (45 tests, nine negative controls) |

### 8.1 The artefact is the RAW config, and the noise floor is why

The gate compares the **raw config as Oxidized stores it** against the
golden, never the sanitiser's output.

Both raw-Oxidized and golden are *captured running configs* — records of the
device. The sanitised file is **derived**: it adds its own
`! <host> - from Oxidized HEAD <sha>` header, re-injects `no shutdown` into
every addressed interface, appends `crypto key generate rsa` for switches and
drops some twenty-five classes of line. Comparing a transformation against its
own input reports **every sanitiser rule as drift**, permanently, on every
device. The header is only the loudest of them; the injected lines are
ordinary configuration and would survive any normalisation.

It also makes the gate independent of the sanitiser, so changing a sanitising
rule cannot make the gate fire.

### 8.2 The measurement corrected the noise-floor claim TWICE, and the second correction is the useful one

**First claim:** *the header is free, because `strip_for_diff` drops comments.*
Measured — it does not. It drops bare `!` and keeps `! text`.

**Second claim, after measuring:** *so the golden's own
`! Golden config — <host> (<ip>)` header fires.* Also wrong, and in the more
interesting direction: that exact prefix **is** in `DIFF_PREFIXES`, so NMAS's
own header was handled years ago.

What is not handled is **Oxidized's** metadata header — the side this project
does not write, and therefore the side nobody ever built a prefix list for.
Without `normalize.strip_provenance_comments()` the gate fires on that one line
for every device on every run: *the noise floor arriving inside the artefact
chosen to avoid it.*

`strip_provenance_comments()` is a **fifth filter job**, not an addition to
`strip_for_diff`, which feeds restore baselines and the drift diff where a
captured config's comments are part of what was captured.

### 8.3 The gate could not reach its own finding, and a control aimed elsewhere found it

The first version fetched Oxidized's timestamps **only on the signal path**.
On the gate path there were none, so every device whose content differed came
back `inconclusive`: the gate could never say *"a change nobody approved"*, and
could never tell one from a poll race. **It would have refused every
difference, benign races included — which is exactly how a gate gets switched
off**, the hazard §4 was written to avoid, reintroduced by the implementation
of the thing that warns about it.

**No test asserting a refusal could see it**, because it refused either way.
What saw it was a negative control aimed at something else: forcing an unknown
timestamp to read as a poll race broke the route test asserting **409**, and
that test had no business depending on a timestamp at all.

The generalisation: **a refusal that is correct for the wrong reason is
invisible to every test that asserts the refusal.** Its siblings are already
recorded — `failed_checks: []` beside `failed_before_any_change` was the same
family with the reason *absent*; here the reason was **present and wrong**,
which is worse, because it sends the reader to fix a timestamp.

The control that found it is the second time this session that a control fired
on a test other than its target. Both times the surprise was the finding.

### 8.4 Resolving an authorisation path must not create a list

`_authorisation_path()` is read on the comparison path for every device.
Written with `get_list_data_dir()` it called `os.makedirs()`, so **asking
whether a divergence was authorised brought a list into existence**. Caught by
the conftest guard, as a test error rather than a wrong answer.

The known rule, in a new place: this was a **read** path, where the hazard is
easiest to overlook precisely because nothing about the call looks like a
write.

### 8.5 What the gate deliberately does not block

`poll_race` — content differs and the **golden** is newer — does not refuse.
The copy about to be written predates an approved change rather than carrying
an unapproved one, and it self-corrects at Oxidized's next poll. It is named,
counted, and says what it costs ("a startup config that predates the approved
change"), which is the difference between not blocking and not mentioning.

### 8.6 The way through, and why it is not a switch

`POST /freshness/authorise`: a **person** (not a service — writing an
unapproved state into what a device boots with is the same act as approving a
deploy), a reason, and the **fingerprint of that one divergence**. It expires
in 24h.

A per-device flag would let the *next* divergence through while the gate
reported `authorised` — a wrong thing wearing a passing result. There is no
`--force`, no settings toggle, and a test parses the module to assert no such
name exists. That test was itself a finding: its first version was a substring
search and matched the module's own paragraph explaining why there is no
switch.
