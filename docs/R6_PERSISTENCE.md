# r6 and the persistence chain — scope

**The deadline set in [R6_PHASE1.md](R6_PHASE1.md) §0c**: r6's lab joins
clab-sync **before phase 2 begins**, or phase 1's "does not establish"
section stands as the permanent record that the device is not reboot-safe.

This scopes the first. Nothing here is built.

---

## 1. What is actually broken, and it is more than the sync

clab-sync harvests from Oxidized and writes to `~/labs/lab/configs/`. r6's
startup config is at `~/labs/r6/configs/r6.cfg` — **a different lab, a
different path**. So a clab host reboot brings r6 back on its bootstrap
config: `password 0`, no rotated credential, NMAS locked out of a device it
manages. Stage B's failure by another route, live since step 6.

**Reading the code found a second half that is worse**, because it fails by
passing rather than by failing. Three settings describe **one** lab:

| setting | default | what it is for r6 |
|---|---|---|
| `clab_configs_dir` | `labs/lab/configs` | wrong — r6 is `labs/r6/configs` |
| `clab_launch_patch` | `labs/lab/patches/c8000v-launch.py` | **wrong, and dangerous** |
| `clab_host` | *(the clab VM)* | correct — one host, two labs |

`verify_startup_file()` and `verify_startup_applies()` both resolve these
**inside the function** when the caller passes nothing, so today they read
`labs/lab/configs/r6.cfg`, which does not exist, and fail closed. That is
survivable.

**The launch patch is not.** `verify_startup_applies()` is the guard that
keeps the rcn-lab1 redeploy ban lifted: it refuses a `secret` line written
into a startup file on a platform whose launch path injects a password
first. Point it at `labs/lab/patches/c8000v-launch.py` while r6 actually
boots from `labs/r6/patches/c8000v-launch-adopted.py`, and **it verifies a
file that is not the one in play and passes** — the precise hazard it
exists to prevent, wearing a green result. Fixing only the configs
directory would *create* that state, because the failure that hides it
today is the missing config file.

## 2. A second target, or a device → lab map

**The map.** Four reasons, in order:

1. **Phase 1 established "onboarded into its own lab" as the pattern**, not
   as an exception. A second target stops generalising at two: the next
   device needs a third, and each is a settings key nobody looks at.
2. **The machinery already exists and one caller is not using it.**
   `verify_startup_file(hostname, hash, *, clab="", remote_dir="")` and
   `verify_startup_applies(..., remote_dir="", launch_patch="")` are
   **already parameterised per call** — only the *defaults* are
   installation-wide. This is the sixth instance of that class in this
   project, and it clusters at the edges of a feature exactly as the others
   did.
3. **Three settings describe one lab and must move together.** Split them
   and you get the launch-patch state above, which is the worse failure.
4. **Lab membership is a per-device fact**, and the manifest is already the
   per-device identity map carrying `platform` "sourced from the
   inventory". It is the same kind of fact in the same place.

### Shape

* **Settings** gain `clab_labs`: `{name: {host, configs_dir, launch_patch,
  sync_script}}`. The existing four `clab_*` keys become the definition of
  the lab named `default`, so **every install keeps behaving exactly as it
  does** — the rule that every new default reproduces the behaviour that
  predates the setting, which this one can honour (unlike
  `netbox_excluded_vrfs`).
* **Manifest** gains `clab_lab` per device. **Absent means `default`**, so
  the nine are untouched without editing anything.
* **One resolver**, `clab_target_for(list_name, hostname)`, returning all
  four values together. `platform_for_device()` is the precedent and the
  reason: *a second copy of the mapping is how the two come to disagree*, and
  a test should assert there is exactly one.
* **Callers pass the resolved target** rather than falling through to a
  default. The defaults stay for a device the map does not name — but a
  device in a *non-default* lab that resolves to the default path is the
  failure this whole item is about, so the resolver returns the lab **name**
  too and the verification records which lab it checked.
* **`run_sync()` runs once per distinct lab** among the devices it covers,
  not once.

### The dependency I cannot satisfy from here

**The sync script lives outside this repository** and today writes to one
directory with no argument. Either it accepts a target directory, or it
learns the map itself. Until one of those is true, NMAS resolving the right
path changes nothing about where the file lands — **so the scoping above is
necessary and not sufficient**, and building the NMAS half alone would
produce a system that verifies the correct path and still writes the wrong
one.

## 3. Acceptance — the original sync's, plus the one it did not need

1. **r6's startup file carries `secret 9` and not `password 0`**, verified
   by **reading the file** on the clab host, not by the sync reporting
   success.
2. `verify_startup_applies("r6", ...)` passes **against r6's own launch
   patch**, and the result **names the file it read**. A pass that does not
   say which patch it checked is the state §1 describes.
3. The redeploy checklist's **item 4.5 applies to r6** on the next reboot.
4. **A control**: pointing r6 at the default lab's patch must make (2)
   fail. A guard that passes for a device in either lab is checking nothing.

## 4. The asymmetry, recorded

**Nine devices survive a reboot because a pipeline built weeks ago covers
them. The tenth does not, because it was added by a newer path that did not
inherit it.**

That is the drift check's *"coverage inherited, not designed"*, again: the
nine reference devices were drift-checked only because their pre-migration
files happened to sit in the legacy directory, and a device onboarded after
the migration was checked by nothing while its config sat in `config_repo/`.

The generalisation is worth more than either instance: **a property that
holds for the original population and silently does not for anything added
afterwards.** It is invisible precisely because the original population is
the one anybody looks at, and it is produced by the same thing every time —
a capability wired to a *list that was current when it was built* rather
than to the population as it is now.

Both instances were found by adding one member. That is the cheapest
available test for this class, and it is what onboarding r6 was always
going to be good for.

---

## 5. The sync half — it ASKS, it does not keep a copy

The sync is `~/lab-configs/oxidized-to-config.sh`, `~/bin/clab-sync` and
`clab-sync.timer`, so both halves are ours. Scoped together so neither
ships alone.

**It asks the NMAS.** A second copy of the device → lab map is how the two
come to disagree — the rule that produced `ListRef` and the tag-slug import,
and the reason `platform_for_device()` is the only translator. A map in the
sync would be a second producer of the same fact, and the failure would be
invisible: the file lands somewhere plausible and the device boots wrong
only at the next reboot.

### The endpoint

`GET /clab/sync_targets` → one line per device, the simplest thing a shell
script can consume without a JSON parser:

```
r1	labs/lab/configs	rcn-lab1
…
r6	labs/r6/configs	r6
```

Plus `GET /clab/sync_targets?format=json` for anything that wants the lab
definitions whole. It reveals **paths, not secrets** — the same class as the
posture panel's gate states, and it is a read, so it is not identity-gated.

### The failure mode of asking, and the only acceptable answer to it

**If the NMAS cannot be reached, the sync skips that device and says so. It
does not fall back to a default directory.**

That is the whole design. A fallback is a guess about where a config boots
from, and a wrong guess writes a device's credentials into another lab's
directory — the same class as `_ensure_ip_address` matching by value, and
the same class as `PipelineContext.list_name` being re-derived. A cached
last-good answer is a second copy wearing a different name, so there is no
cache either.

`clab-sync` therefore exits non-zero when the map is unavailable, and the
timer unit's failure is the signal. **A sync that silently covered eight of
ten devices is the "coverage inherited, not designed" shape one more time**,
and it is the thing this item exists to remove.

### What each piece changes

| piece | change |
|---|---|
| `settings_schema` | `clab_labs` mapping; existing `clab_*` become the lab `default` |
| `manifest` | `clab_lab` per device; absent ⇒ `default` |
| `credential_rotation` | one resolver, passed to the three verifiers and to `run_sync` per lab |
| `routes/` | `GET /clab/sync_targets` |
| `oxidized-to-config.sh` | takes a target directory per device instead of one constant |
| `~/bin/clab-sync` | fetches the map, iterates, **refuses on an unreachable NMAS** |

---

## 6. The window: what happens if one half ships first

**Measured, not assumed, because the answer decides whether they must land
together.** They do not — **both single-half windows fail closed** — but one
of them is safe for a reason that was not designed, and that is worth more
than the answer.

### NMAS half first, sync unchanged

The resolver points the checks at `labs/r6/configs/r6.cfg`. That file
**exists** — the operator wrote the bootstrap artefact there in phase 1 —
and holds `password 0`, not the rotated `secret 9`.
`verify_startup_file()` greps for the new hash, does not find it, and the
chain stops. **Fails closed.**

The unchanged sync still writes `labs/lab/configs/r6.cfg`: inert, because
rcn-lab1's topology does not reference it, but **litter that looks like a
startup config for r6** and should be removed when the sync half lands.

### Sync half first, NMAS unchanged

The sync writes the right file; the checks still read
`labs/lab/configs/r6.cfg`, which is absent, and the chain stops. A **false
negative** — safe, and it would send somebody chasing a problem that no
longer exists.

### The partial state I identified is NOT reachable

Only because the map moves all three settings **together by construction**.
Fixing `clab_configs_dir` alone was the dangerous version, and the map makes
that combination unrepresentable rather than merely unlikely.

### But there is one, and the ordering is what stops it

`verify_startup_applies()` on that same bootstrap file returns
**`ok: True, applies: True`** — a `password` form *does* apply behind
vrnetlab's injected line, and the device really does end up holding it. The
function answers its own question truthfully. **Its question is not "is this
device reboot-safe with the credential NMAS holds."**

It is never reached, because `persist()` runs presence **before**
applicability and returns on failure — an ordering written for a different
reason entirely ("presence is not applicability", after Stage B). So the
window fails closed on a property this chain **inherited rather than
designed**, which is the third shape of that kind in one night.

`TestThePersistenceChainFailsClosedOnAHalfDeploy` pins it: the ordering, the
short-circuit, that `applies` really does say yes to a bootstrap file, and
that presence really does say no to the same file. Swapping the two stages
fails it.

**So the halves may ship separately, in either order**, and the ordering
assertion is what keeps that true.
