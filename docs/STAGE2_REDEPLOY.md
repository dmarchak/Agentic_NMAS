# Stage 2 — lifting the redeploy ban

> **For the session itself, use
> [docs/STAGE2_SESSION_CHECKLIST.md](STAGE2_SESSION_CHECKLIST.md)** — one
> self-contained document, in order, with the boxes to tick. This file is the
> reasoning behind each item; that one is what you run.
>
> **2.3 (stage D) has moved to Stage 4.** It tests `crypto key generate rsa`
> in the *generator's* output for r6. No harvested config contains that line —
> `show running-config` never emits it — so the redeploy does not involve it.

**Written for: Dustin, at the machine, running these by hand.** Nothing here
is automated and nothing here should be run by an agent. Every step that
touches shared infrastructure is yours.

**Read this whole file before starting 2.4.** The checklist exists because it
was written *before* the redeploy, and a checklist written afterwards is a
description of what happened.

> **The ban lifts on a successful redeploy, not on these items being built.**
> Items 2.1–2.3 make the redeploy survivable. 2.4 is the proof.

---

## Before anything: the state this assumes

| | expected |
|---|---|
| NMAS deployed at | `a978a5c` or later (Stage 1 complete) |
| `config_repo` HEAD | `2443892`, published |
| rcn-lab1 nodes | running since 2026-09-19, **never rebooted since the rotation** |
| `~/labs/lab/configs/r1–r5.cfg` | contain `username admin privilege 15 secret 9 $9$…` |
| `~/labs/lab/patches/c8000v-launch.py` | stock + `smp="2"`, **no user skip** |

If any of these is not true, stop and say so — particularly the third. The
whole hazard is that those files have never been booted.

---

## 2.1 Adopt the launch patch

The patch is **copied, edited, reviewed, then swapped in.** The production
file is never edited in place; the patcher refuses a path under `~/labs/lab`.

```bash
cd ~/labs/lab/patches
cp c8000v-launch.py /tmp/c8000v-launch-userskip.py
cp c8000v-launch.py ~/c8000v-launch.py.pre-userskip.bak   # keep the original

# Show the diff. Writes nothing.
python3 ~/python/Agentic_NMAS/docs/bootstrap-probe/patches/patch-skip-injected-user.py \
    /tmp/c8000v-launch-userskip.py

# Apply it to the COPY.
python3 ~/python/Agentic_NMAS/docs/bootstrap-probe/patches/patch-skip-injected-user.py \
    /tmp/c8000v-launch-userskip.py --write

# What changed, against the file in use.
diff ~/labs/lab/patches/c8000v-launch.py /tmp/c8000v-launch-userskip.py
```

### The diff you should see

Two functional lines at the concatenation site, plus the helper:

```diff
     def bootstrap_spin(self):
         startup_cfg = self.read_startup_config()
-        cfg = self.gen_bootstrap_config() + startup_cfg
+        cfg = _skip_users_defined_in_startup(
+            self.gen_bootstrap_config(), startup_cfg) + startup_cfg
         self.write_config(cfg)
```

plus, at module scope above the first class, `_skip_users_defined_in_startup()`
— which drops a `username X …` line from **vrnetlab's** bootstrap block when
the startup config defines that same user, and leaves every other user alone.

### If the patcher refuses

It refuses rather than guessing when the file is not what stage B measured:
already patched, no `import re` / `import logging`, no
`username … privilege 15 password …` line, not exactly one
`cfg = self.gen_bootstrap_config() + startup_cfg`, or the file not parsing.

**A refusal means the reading this fix rests on is stale. Report it; do not
force the edit.** (A line-anchored import check was itself a source of false
refusals and was fixed in `fda8136` — if it refuses now, it is about the
file.)

### Swapping it in

```bash
cp /tmp/c8000v-launch-userskip.py ~/labs/lab/patches/c8000v-launch.py
grep -c '_skip_users_defined_in_startup' ~/labs/lab/patches/c8000v-launch.py   # 2
grep -n 'smp=' ~/labs/lab/patches/c8000v-launch.py                            # smp="2"
```

**Running nodes are unaffected.** Binds are read at container start, so this
changes nothing until a redeploy — which is why it is safe to adopt now and
verify later.

---

## 2.2 The applicability check and the break-glass record

### 2.2a — prove the applicability check on a real rotation

`verify_startup_applies()` is built and tested and **nothing in the running
app calls it** until a rotation runs. It reads the launch script on the clab
host and decides whether a `secret` line in a startup file can apply.

One new setting is involved. Confirm it points at the file you just patched:

```bash
grep clab_launch_patch ~/python/Agentic_NMAS/data/user_settings.json
# expect: "labs/lab/patches/c8000v-launch.py"
```

Then rotate **one** device — a switch, where nothing is injected and the
stage short-circuits, then a router, where it does the real work:

```bash
python3 scripts/nmas-rotate-credential --list Default --device s1   # expect: startup_applies ok
python3 scripts/nmas-rotate-credential --list Default --device r1   # the real test
```

`r1`'s `startup_applies` stage should pass **because the launch script now
carries the skip**. To prove the check is measuring and not merely agreeing:

```bash
# Temporarily hide the marker, re-run the persist chain only, expect a REFUSAL.
sed -i 's/_skip_users_defined_in_startup/_skip_users_defined_in_startupX/g' \
    ~/labs/lab/patches/c8000v-launch.py
python3 scripts/nmas-persist-credential r1 --dry-run     # expect startup_applies to FAIL
sed -i 's/_skip_users_defined_in_startupX/_skip_users_defined_in_startup/g' \
    ~/labs/lab/patches/c8000v-launch.py
python3 scripts/nmas-persist-credential r1 --dry-run     # expect it to PASS again
```

**A check that only ever passes has not been shown to work.** If it passes
with the marker hidden, it is reading something else and Stage 2 stops here.

### 2.2b — the break-glass record

**What I need from you**, and why each:

| | why |
|---|---|
| a **passphrase**, ≥12 chars, not stored on the NMAS | it is the only key; `data/key.key` is deliberately not involved, or the record would share a failure with the thing it recovers |
| a **destination outside the repository**, on removable media | `config_repo` is pushed to a private remote; the tool refuses any path inside a git repo |
| **where you will record its location** | somewhere that is not the NMAS — the record is useless if finding it requires the machine you are recovering from |

```bash
cd ~/python/Agentic_NMAS
python3 scripts/nmas-breakglass export --list Default --out /media/<usb>/rcn-breakglass.bg
```

It prints the device list and a warning, asks for the passphrase twice, and
writes mode 600. Then — **on the medium it will live on**:

```bash
python3 scripts/nmas-breakglass verify /media/<usb>/rcn-breakglass.bg
```

Expect nine devices, `pw: yes` for each, `complete: True`, and **no credential
printed**. The digest is salted per hostname, so two devices sharing a
password do not show the same token.

> **An untested break-glass record is a hope, not a record.** The verify step
> is not optional, and it must run against the file where it will live, not
> the copy that was just in memory.

**Closed by measurement, 2026-09-22.** Exported for `Default`, verified on the
NMAS, copied to the laptop with a matching sha256, and **verified again there**
— nine devices, password and enable secret each, `complete: True`, no value
printed. Passphrase and location in the password manager; the NMAS copy
deleted. The laptop verify is the one that mattered: a matching sha256 proves
the bytes, not that the record can be opened on a machine you will still have
when the one you are recovering from is the problem.

`reveal` exists for the outage itself and prints one device at a time. Do not
run it now.

---

## 2.3 Stage D — the generator fixes, on the probe

`crypto key generate rsa` is **unmeasured on a console-replayed platform**.
vrnetlab types a vIOS startup config into the console line by line and waits
for a prompt after each; key generation takes real time. Nobody has watched
one do it.

Same isolation as stages A–C: own lab name, own network, destroyed after.

```bash
cd ~/labs/bootstrap-probe
# The generator's own output, for a throwaway switch.
python3 - <<'EOF'
import sys; sys.path.insert(0, '/home/dustin/python/Agentic_NMAS')
from modules.nsot.bootstrap_config import render_bootstrap
open('configs/bp-vios-d.cfg', 'w').write(render_bootstrap(
    'cisco_ios', hostname='bp-vios-d', username='admin', secret='admin'))
EOF
cat configs/bp-vios-d.cfg          # confirm: crypto key line present, no prose comments
containerlab deploy -t nmas-staged-probe.clab.yml
```

Pass criteria — **the capture must come over SSH, not the console.** That is
the whole point of the key:

```bash
c=clab-nmas-staged-probe-bp-vios-d
time docker logs -f $c 2>&1 | grep -m1 "Startup complete"      # expect < 15 min
docker logs $c 2>&1 | grep -i "crypto key\|RSA"                # did it generate?
ssh -o StrictHostKeyChecking=no admin@<probe-ip> 'show ip ssh' # SSH, not telnet
```

Then a C8000v with `ip domain name`, confirming no `%CVAC-4-CLI_FAILURE`.

**If key generation stalls the console replay**, that is the finding stage D
exists for — report where it stops, and the generator emits the key line
somewhere other than the startup config (a post-boot step), which is a design
change, not a retry.

Destroy afterwards, and remove the generated configs.

---

## 2.3b Stage D2 — has a vIOS ever booted a `secret 9` line?

**Measured answer: no.** The only vIOS ever booted (`bp-vios`, stage A)
carried `username admin privilege 15 secret 0 admin` — *plaintext*, which IOS
hashes on entry. Every `secret 9` boot so far was a **C8000v**: `bp-c8k-b`
(stage B) and `bp-c8k-c` (stage C), both single-node router topologies.

So the switches are as unproven as the routers were, on **two** properties —
and only the first is shared with the routers:

1. **Consumption.** The rotation sends
   `username admin privilege 15 algorithm-type scrypt secret <plaintext>`, so
   the **device computes** the hash. `clab-sync` then harvests
   `show running-config`, which emits `secret 9 $9$salt$hash` into the startup
   file. **The device emits a form it has never been asked to read back at
   boot.** That was equally true of the routers until stage B.
2. **Console replay.** vrnetlab *types* a vIOS startup config into the console
   line by line, waiting for a prompt after each; the routers' file is loaded
   as a file. This is the platform where a comment hung a boot. The routers'
   proof does not transfer, because the mechanism differs.

> Without D2, **the redeploy is the first test of four switches at once** —
> which is precisely what stage B taught us not to do.

### D2, by stage B's method, on the other platform

The hash must come from a vIOS, and only a device can produce one.

```bash
cd ~/labs/bootstrap-probe
# 1. Boot the KNOWN-GOOD vIOS shape (stage A's, already proven).
cp configs/bp-vios.cfg configs/bp-vios-d2.cfg
containerlab deploy -t nmas-vios-d2.clab.yml
```

On the node, generate a throwaway type-9 hash and remove the scratch account:

```
configure terminal
username hashgen privilege 1 algorithm-type scrypt secret ProbeSecretValue2
do show running-config | include ^username hashgen
no username hashgen
end
```

```bash
# 2. Destroy, fill the template with that hash, redeploy.
containerlab destroy -t nmas-vios-d2.clab.yml --cleanup
sed "s|@@HASH@@|<the $9$ token>|" configs/bp-vios-secret9.cfg.template \
  > configs/bp-vios-d2.cfg
grep -c '@@HASH@@' configs/bp-vios-d2.cfg      # must print 0
containerlab deploy -t nmas-vios-d2.clab.yml
```

### Pass criteria

```bash
c=clab-nmas-vios-d2-bp-vios-d2
time docker logs -f $c 2>&1 | grep -m1 "Startup complete"    # expect < 15 min
docker logs $c 2>&1 | grep -iE "invalid|rejected|%.*ERROR"   # expect nothing
sshpass -p 'ProbeSecretValue2' ssh -o StrictHostKeyChecking=no \
  admin@<probe-ip> 'show running-config | include ^username admin'
```

- [ ] `Startup complete` reached
- [ ] **no** refusal for the username line in the boot log
- [ ] running config shows `secret 9`, not `secret 0` and not absent
- [ ] `ProbeSecretValue2` is **accepted** over SSH
- [ ] the replay did not stall — the whole config applied, not just the part
      before the username line

**If the line is refused**, the switches are in the routers' pre-stage-C
position and the redeploy must not proceed for them. The fix is not the same
one: no username is injected on vIOS, so the cause would be the *hash form or
the replay*, not coexistence — measure which before designing anything.

The template carries **no prose comments**, like stage A's. A first draft of
it had nineteen, which on this platform is nineteen lines typed into a console
for no reason — the exact shape that hung run 2. A test now enforces it for
every `vios` config in the probe directory.

---

## 2.4 The redeploy, and its checklist

**Written before the redeploy. Do not edit it afterwards to match what
happened** — if an item fails, the ban stays and the failure is measured.

### Before

- [ ] 2.1 adopted, `smp="2"` and the skip both present in the bound file
- [ ] 2.2a passed **and** demonstrated failing with the marker hidden
- [ ] 2.2b record written, verified **on the USB stick**, location noted off-box
- [ ] 2.3 passed, or its failure understood and the generator changed
- [ ] **2.3b (D2) passed** — a vIOS has booted a `secret 9` startup line.
      Without this the redeploy is the first test of four switches at once
- [ ] `config_repo` clean and pushed — `git status` clean, local HEAD == remote main
- [ ] A **Save All** run now, so the pre-redeploy goldens are the comparison point
- [ ] `~/labs/lab/configs/r1–r5.cfg` still carry `secret 9` (`grep -c 'secret 9'` → 5)
- [ ] You are at the machine and have time to finish

### The redeploy

```bash
cd ~/labs/lab
containerlab destroy -t rcn-lab1.clab.yml --cleanup
containerlab deploy  -t rcn-lab1.clab.yml
```

### After — every item, in order

1. [ ] **All nine nodes reach `Startup complete`.** Routers ~5–7 min, switches
       ~4–5. Anything past **15 minutes is a failure**, not slowness.
1b. [ ] **Each device's uptime is consistent with the redeploy.**
        `show version | include uptime`, per device.

        On the D2 probe a vIOS took a CPU exception (PnP Agent Discovery,
        SIGBUS) and **silently reloaded**: the container stayed healthy,
        `docker logs` said nothing, and only uptime revealed it. A node that
        reloaded after its config was applied is a node whose running config
        may not be what the log says was applied — and `Startup complete`
        will have been printed by the *first* boot.
2. [ ] **No `%CVAC-4-CLI_FAILURE` for a username line** on any router:
       `docker logs <node> 2>&1 | grep CVAC`
3. [ ] **The skip fired** on each router:
       `docker logs <node> 2>&1 | grep -i "not injecting"`
4. [ ] **Each router's running config shows `secret 9`**, not `password 0`:
       `show running-config | include ^username admin`
4b. [ ] **Each switch's too.** Nothing is injected on vIOS, so the failure
        mode differs — a refused hash or a stalled console replay, not
        coexistence. Check the boot log as well as the running config.
5. [ ] **Each device answers with the credential NMAS holds**, and the old
       `admin`/`admin` is **REFUSED** on the routers. *This is the item the
       whole stage exists for*, and it is the one that was broken.

       **Do not use `ssh`/`sshpass` for this.** On the D2 probe the refusal
       line passed because the connection died at **key exchange** — a modern
       OpenSSH against a 2018 image — so `ssh` exited non-zero and the check
       printed PASS. It would print PASS with the device powered off, and it
       would print PASS here while every router sat on `admin/admin` and
       unreachable. A two-valued check on a remote system can pass by not
       asking.

       Use the app's own connection path, which answers in **three** values
       and negotiates the way NMAS negotiates:

       ```bash
       for d in r1 r2 r3 r4 r5 s1 s2 s3 s4; do
         python3 scripts/nmas-check-credential $d --expect accepted || break
       done
       for d in r1 r2 r3 r4 r5; do
         python3 scripts/nmas-check-credential $d --password admin --expect refused || break
       done
       ```

       `INCONCLUSIVE` (exit 2) is **not** a pass. It means nothing was
       established — find out why before reading anything into it.
6. [ ] **Oxidized fetches all nine**, with times after the redeploy.
7. [ ] **A Save All produces no unexpected diff** against the pre-redeploy
       goldens. Interface counters and uptime aside, a difference here means a
       node did not come back as itself.
8. [ ] **Drift check runs clean** — noting it covers only the nine legacy
       entries (Stage 3.3).
9. [ ] The Remote card shows the post-redeploy Save All pushed.

### If any item fails

Stop. **Measure before changing anything** — logs, running config, which
credential the device answers on. The break-glass record and the console
(`docker exec -it <node> telnet localhost 5000`) are the way in.

Do **not** redeploy again to "try it clean". A second redeploy destroys the
evidence of why the first failed.

### Only when every item passes

Update the three ban notices — `CLAUDE.md`, `docs/bootstrap-probe/README.md`,
`docs/NSOT_PHASE4_ONBOARDING.md` — to **"lifted on <date>, and here is what
proved it"**, with the checklist result. Not deleted: the reasoning is why
the next person does not re-create the hazard.
