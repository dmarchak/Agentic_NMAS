# Measuring the bootstrap profile

> ## ✅ REDEPLOY BAN LIFTED — 2026-09-22
>
> **Lifted by a successful redeploy, not by the fix being built.** Here is
> what proved it.
>
> The ban existed because `configs/r1.cfg`–`r5.cfg` carried
> `username admin privilege 15 secret 9 …` and had never been booted. Stage B
> measured, on a throwaway C8000v, that vrnetlab's injected
> `username admin privilege 15 password admin` lands first and IOS-XE refuses
> a secret for a user that already has a password: the node came up on
> `admin/admin`, reached `Startup complete`, reported healthy, and answered
> SSH — with a startup file that read correctly and did not apply.
>
> **The redeploy of 2026-09-22, 23:39:**
>
> | | result |
> |---|---|
> | all nine `Startup complete` | routers ~6m30, switches 4m17–5m09 |
> | uptimes | consistent with this boot; no silent reload |
> | username line rejected | **none** |
> | the user-skip fired | exactly once on every router |
> | `secret 9` on all nine | yes; **no device holds `password 0`** |
> | the credential NMAS holds | **accepted on all nine** |
> | old `admin`/`admin` | **refused on all five routers** (`NetmikoAuthenticationException`) |
> | Oxidized | nine successes, all after the redeploy |
> | Save All vs pre-redeploy goldens | `758d1f56` — certificate bodies on r1–r5 only; **zero non-certificate changed lines** |
> | drift | clean, 9/9 |
>
> **What made it safe to try**, in order: the launch patch adopted into
> `~/labs/lab/patches/` (stage C); a break-glass credential record verified on
> the laptop it lives on; stage D2 proving a vIOS boots a real `secret 9`
> startup line, so the switches were not tested for the first time by the
> redeploy itself; and an applicability check whose **negative control was
> watched to fail** — routers `WILL NOT APPLY` with the marker hidden,
> switches unaffected.
>
> That last one nearly did not happen. The check's first version reported
> APPLIES with the marker hidden, because it searched for a *name* rather than
> a call. Nine APPLIES lines were about to enter this record as evidence.
>
> **Kept, not deleted.** The reasoning is what stops the hazard being
> recreated — by a rotation that writes a `secret` line into a startup file on
> a platform whose launch path injects a password first. The persistence
> chain's `startup_applies` stage now refuses that at the moment it would be
> created.

The Phase 4 wizard decides whether a device is *factory-default* or *already
configured*. That decision needs a per-platform **bootstrap profile**: the set
of lines the image and containerlab create on a node nobody has touched.

The profile must be **measured**. A profile that lists too much blocks every
real deploy; one that lists too little passes a configured device off as new.
Neither error is visible by reading the code that produced the list, and
neither is visible in testing against devices that are already configured —
which is all nine of ours.

Nothing in this directory has been run. It is a proposal for shared
infrastructure.

**Revised after the first attempt failed.** See "What the first probe got
wrong" below — both causes were divergences from `rcn-lab1` that the first
version claimed to mirror and did not, which is worth more than the fix.

---

## Why a separate topology

`rcn-lab1` is the production lab. Its nodes are configured, which makes them
useless for this measurement, and it is the thing the whole project manages,
which makes experimenting in it a bad trade.

`nmas-bootstrap-probe.clab.yml` shares no *state* with it, while matching
everything that affects how a node boots:

| | rcn-lab1 | the probe |
|---|---|---|
| lab name | `rcn-lab1` | `nmas-bootstrap-probe` |
| docker network | default `clab` | `clab-bootstrap-probe` |
| subnet | 172.20.20.0/24 | 172.30.30.0/24 |
| startup configs | per node | per node, **minimal** |
| c8000v launch patch | bound from `patches/` | **copied** into its own dir |
| nodes | 9 + hosts | 2 |

The separate subnet is not fussiness. `rcn-lab1` carries a comment explaining
that it has no `mgmt:` block *because* declaring a second network on
172.20.20.0/24 fails with "Subnet already in use by Docker network clab". A
probe lab that reused the subnet would either fail to deploy or attach to the
production network.

**Headroom checked before proposing:** 196 GB free on `/var/lib/docker`, 51 GB
free RAM. Two nodes (one C8000v, one vIOS-L2) fit comfortably.

---

## Commands

Run on `10.0.0.210`. Steps 2 and 6 are the only ones that change anything,
and step 6 undoes step 2.

### 1. Stage the files

The launch patch is **copied**, not referenced. A read-only bind from
`~/labs/lab` would still be a shared file, and a throwaway lab whose
destruction can touch the production lab is not throwaway.

```bash
mkdir -p ~/labs/bootstrap-probe/{configs,patches,captures}
cd ~/labs/bootstrap-probe
cp ~/labs/lab/patches/c8000v-launch.py patches/
# copy nmas-bootstrap-probe.clab.yml here, and configs/bp-*.cfg into configs/

# Confirm the patch is the one rcn-lab1 uses — one line, smp="2".
diff ~/labs/lab/patches/c8000v-launch.py patches/c8000v-launch.py && echo "patch identical"
grep -n 'smp=' patches/c8000v-launch.py
```

### 2. Deploy, and watch for the thing that failed last time

```bash
containerlab deploy -t nmas-bootstrap-probe.clab.yml
```

Measured on rcn-lab1: **r1 completes in 5m19s, s1 in 4m38s.** Anything past
**15 minutes is a failure**, not slowness — the first probe sat for ~40
minutes and was never going to finish.

```bash
# Both nodes, with a hard deadline. Prints the line that decides it.
end=$(( $(date +%s) + 900 ))
for n in bp-c8k bp-vios; do
  c=clab-nmas-bootstrap-probe-$n
  while [ "$(date +%s)" -lt "$end" ]; do
    if docker logs "$c" 2>&1 | grep -q "Startup complete"; then
      echo "$n: $(docker logs "$c" 2>&1 | grep -m1 'Startup complete')"; break
    fi
    sleep 15
  done
  docker logs "$c" 2>&1 | grep -qE "Startup complete" || {
    echo "$n: FAILED to complete within 15m — capture the reason and stop:"
    docker logs "$c" 2>&1 | tail -20; }
done

# The two symptoms that identified the first failure, checked explicitly:
for n in bp-c8k bp-vios; do
  c=clab-nmas-bootstrap-probe-$n
  echo "--- $n ---"
  docker logs "$c" 2>&1 | grep -iE "startup configuration|SMP|vCPU|memory" | head -5
done
```

`bp-c8k` must report **2 SMP/vCPU** and must *not* say "User provided startup
configuration is not found". If it says either of those, stop: the lab is not
mirroring rcn-lab1 and its capture would describe a node type we do not run.

### 3. Capture

The same command the application uses, so the profile is measured against the
text the wizard will actually compare:

```bash
cd ~/labs/bootstrap-probe/captures
for n in "bp-c8k 172.30.30.11 cisco_iosxe" "bp-vios 172.30.30.21 cisco_ios"; do
  set -- $n
  ssh -o StrictHostKeyChecking=no admin@$2 \
      'terminal length 0 ; show running-config' > "$3.cfg"
  ssh -o StrictHostKeyChecking=no admin@$2 \
      'show version' > "$3.version.txt"
  printf '%s  %s  %s\n' "$1" "$2" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> provenance.txt
done
wc -l *.cfg
```

If SSH is not up but the node is, the serial console is the fallback and needs
no IP path at all:

```bash
{ printf '\r\nterminal length 0\r\nshow running-config\r\n'; sleep 20; } \
  | timeout 60 docker exec -i clab-nmas-bootstrap-probe-bp-c8k telnet localhost 5000
```

### 4. Hand the captures back

```bash
# from the NMAS
scp dmarchak@10.0.0.210:~/labs/bootstrap-probe/captures/'*' /tmp/bootstrap/
```

They land in the repository as fixtures, with their provenance, at
`tests/fixtures/bootstrap/<platform>.cfg`. The profile is derived from them in
code and tested against them, so a future image change is a failing test
rather than a wrong answer.

### 5. Verify the captures are what they claim

Before trusting them: each should contain a hostname, a management interface,
**no routing process**, and **no addressed data interface**. If either capture
shows a routing process, the node is not fresh and the profile must not be
built from it.

### 6. Destroy

```bash
cd ~/labs/bootstrap-probe
containerlab destroy -t nmas-bootstrap-probe.clab.yml --cleanup
docker network rm clab-bootstrap-probe 2>/dev/null || true
```

`--cleanup` removes the lab directory containerlab creates. The explicit
network removal is belt-and-braces: a leftover docker network is harmless but
it is the only thing that would persist.

---

## What the profile will be used for

Per the decision: **"nothing beyond the profile" = factory-default.** A
routing process, or a data interface with an address, means configured —
which the wizard refuses unless the operator acknowledges it.

The profile is per platform, and it records *shapes*, not exact strings:
`hostname <anything>`, a management interface with an address, a
containerlab-created user, the `clab-mgmt` VRF if present, and unaddressed
interface stubs in any number. Recording exact strings would make the profile
break on a hostname, which is the one line guaranteed to differ.


---

## What the first probe got wrong

Worth recording, because the fix is small and the mistake is not.

| | rcn-lab1 | first probe | effect |
|---|---|---|---|
| startup config | every node | **none** | different vrnetlab path; vIOS never got a management address |
| c8000v vCPUs | 2, via a bound launch patch | **1** (stock) | never completed in ~40 min; r1 takes 5m19s |

The first version of this file said it mirrored `rcn-lab1` and listed the
things it had matched: images, kind env, network isolation. Everything on that
list was correct. The two things that mattered were not on it, because they
were not in the part of the topology I had read — `binds:` and
`startup-config:` are per *node*, and I had read the `kinds:` block and
inferred the rest.

> "Mirrors X" is a claim about everything X does, and it is only as good as
> the part of X you looked at. Approximating an environment reproduces the
> parts you already knew about, which are exactly the parts that were never
> going to be the problem.

The vIOS failure is the sharper one. Its management interface works *because
a startup config asks it to* — `CLAB_MGMT_PASSTHROUGH=false` plus
`ip address dhcp` on Gi0/0. A "clean" node with no configuration at all is
therefore not a fresh node in this lab; it is an unreachable one. There is no
such thing as an unconfigured vIOS here, and a bootstrap profile that assumed
otherwise would have been measuring a device that never exists.

## The minimal bootstrap config is the wizard's output

`configs/bp-c8k.cfg` and `configs/bp-vios.cfg` are not probe scaffolding. They
are the management-plane lines of `r1.cfg` and `s1.cfg` with everything else
removed, and they are what the wizard must generate for a new device — so
they are designed once, here, and the probe measures the result.

The asymmetry between them is real and load-bearing: the C8000v's `Gi1` is
absent because vrnetlab owns it, while the vIOS's `Gi0/0` is configured
explicitly because nothing else will. A wizard that treated the two platforms
the same would produce an unreachable switch.

---

## The two platforms bootstrap differently, and it decides the username form

Measured in the launch scripts rather than inferred from behaviour.

| | C8000v | vIOS-L2 |
|---|---|---|
| bootstrap config | `cfg = gen_bootstrap_config() + startup_cfg` | none |
| injects a username line | **yes** — `username admin privilege 15 password admin` | **no** |
| with no startup config | falls back to bootstrap only; boots | `logger.fatal("Failed to find startup configuration file")` |
| username form this file may use | **password** | **secret** |

This explains both of the first probe's failures precisely. The vIOS did not
stall because it was slow — it failed fatally, by design, for want of a file.
And the C8000v's fallback path works, so its failure was purely the missing
second vCPU.

It also settles the username form by mechanism rather than by convention. On
the C8000v, vrnetlab's line lands first, so a `secret` here would arrive at a
user who already has a `password` and be refused — the same refusal measured
on r2 in stage 1. On the vIOS nothing is injected, so `secret` is safe, and a
username line is not optional: without one the node is unreachable.

### A hazard this uncovered, outside the probe

`configs/r1.cfg` … `r5.cfg` in `~/labs/lab` **currently contain `secret 9`**,
harvested after the credential rotation. Those files have not been booted:
r1 and s1 last started **2026-09-19 05:23**, and the files were rewritten
**2026-09-21 18:41**.

On the next redeploy, each router's `secret 9` line would arrive after
vrnetlab's `username admin privilege 15 password admin` and be **refused**.
The routers would come up holding vrnetlab's password, while NMAS holds the
type-9 credential — so NMAS could not log in, and the startup file would look
correct while being unappliable.

The switches are unaffected: nothing is injected there, so their `secret 9`
line is the only one and applies cleanly.

This is the inverse of the hazard the persistence chain was built for. That
chain verifies the new hash **is in the startup file**; it never verified the
file would **apply**. Writing it down here rather than fixing it in passing —
it wants its own decision, and the fix is probably that a C8000v startup file
must carry the password form and let `set_credential` rotate afterwards,
which is exactly what the wizard will do for r6.

---

# Stage B — does r1's current startup file actually apply?

Stage A measures what a fresh node looks like. **Stage B measures whether the
redeploy hazard is real**, because reading a launch script is a prediction and
this one decides whether the production lab can be redeployed.

Run **after** stage A is captured and destroyed. Stage B needs a real type-9
hash, and only a device can produce one.

### B1. Generate a type-9 hash on the probe

While stage A's `bp-c8k` is still up — do this before destroying it.

```bash
PLAIN='ProbeSecretValue1'          # throwaway, known, never the fleet's
ssh -o StrictHostKeyChecking=no admin@172.30.30.11
```

At the prompt:

```
configure terminal
username hashgen privilege 1 algorithm-type scrypt secret ProbeSecretValue1
end
show running-config | include ^username hashgen
```

Copy the `$9$…` token. Then remove the scratch user — it prompts:

```
configure terminal
no username hashgen
<press Enter at "Do you want to continue? [confirm]">
end
```

Now destroy stage A (step 6 above) and stage the hash:

```bash
cd ~/labs/bootstrap-probe
sed "s|@@HASH@@|<the \$9\$… token>|" \
    configs/bp-c8k-secret9.cfg.template > configs/bp-c8k-secret9.cfg
grep -c '@@HASH@@' configs/bp-c8k-secret9.cfg      # must print 0
```

### B2. Boot it

```bash
containerlab deploy -t nmas-redeploy-probe.clab.yml
```

Same 15-minute deadline. Then, **before touching the device**, read the boot
log — the refusal is the evidence, and it is easier to see here than to infer
from behaviour afterwards:

```bash
c=clab-nmas-redeploy-probe-bp-c8k-b
docker logs "$c" 2>&1 | grep -iE "can not have both|invalid|refused|%AAAA|type 0 password" | head
docker logs "$c" 2>&1 | grep -m1 "Startup complete"
```

### B3. Ask the device which credential it has

The whole question, in three attempts. **Expect two of them to fail** — that
is the measurement, not an error:

```bash
for p in admin ProbeSecretValue1; do
  if sshpass -p "$p" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
       admin@172.30.30.31 'show running-config | include ^username admin' \
       >/tmp/out.$p 2>/dev/null; then
    echo "ACCEPTED: $p"; sed -E 's/(secret|password) ([0-9]+ )?\S+/\1 \2<redacted>/' /tmp/out.$p
  else
    echo "refused : $p"
  fi
done
```

If **neither** is accepted, SSH is locked out — which is itself the answer,
and the console still works:

```bash
{ printf '\r\nenable\r\nshow running-config | include ^username admin\r\n'; sleep 10; } \
  | timeout 40 docker exec -i clab-nmas-redeploy-probe-bp-c8k-b telnet localhost 5000
```

### B4. Report, then destroy

| observation | meaning |
|---|---|
| `admin` accepted, running config shows `password` | **hazard confirmed** — the secret line was refused; r1–r5 would come up on vrnetlab's credential |
| `ProbeSecretValue1` accepted, running config shows `secret 9` | hazard **not** real on this image; the reading was wrong and the startup files are fine |
| neither accepted | worse than predicted — record exactly what the running config holds |

```bash
containerlab destroy -t nmas-redeploy-probe.clab.yml --cleanup
docker network rm clab-bootstrap-probe 2>/dev/null || true
rm -f configs/bp-c8k-secret9.cfg          # it contains a generated hash
```

---

## Stage B result: hazard CONFIRMED on hardware (2026-09-21)

Measured, not predicted.

| observation | value |
|---|---|
| Startup complete | reached, 7m26s |
| boot log | `%CVAC-4-CLI_FAILURE: Configuration command failure: 'username admin privilege 15 secret 9 $9$…' was rejected`, preceded by the `%AAAA` type-0 warning for vrnetlab's injected line |
| running config after boot | `username admin privilege 15 password 0 admin` |
| SSH as `admin` | **accepted** |
| SSH with the file's own credential | **refused** |

So the prediction was right in every part, including the part that makes it
dangerous: **the node boots successfully.** `Startup complete` is reached, the
container is healthy, the router answers SSH. Only the credential is not the
one its startup file describes. There is no failure to notice.

A redeploy of rcn-lab1 today brings r1–r5 up on vrnetlab's admin/admin and
locks NMAS out of all five.

### What this says about the persistence chain

`verify_startup_file()` greps the startup file for the new hash and passes.
The hash **is** in the file. The file does not apply. That is a **presence**
check standing in for an **applicability** one, and the gap between them is
exactly the size of this defect — five routers, silently unreachable, at the
next redeploy.

Nothing short of a boot could have distinguished the two. The check was not
weak in a way a reviewer would see; it asked a question whose answer was yes.

---

## The two candidate fixes

Both to be evaluated **on the probe**, not on rcn-lab1. Stage C evaluates
(a).

**(a) Patch the launch script to skip its username injection when the startup
config supplies one.** `patches/c8000v-launch.py` already exists and already
diverges from stock by one line, so this is a second line in a file the lab
owns. It fixes r1–r5 and r6 at the source and keeps the startup files honest —
the file says what the device will have.

Before adopting it, one thing must be checked rather than assumed: **does
vrnetlab still need that account?** It authenticates to the console with
`--username/--password` to apply the config, and the healthcheck may use it
too. Skipping the injection when a startup config defines the same user is
safe only if the startup config's credential is one vrnetlab also knows, or if
nothing after the injection needs to log in. The probe can answer this: patch,
boot, and see whether `Startup complete` is still reached and the healthcheck
still passes.

**(b) The startup file carries the password form, and `set_credential` rotates
after boot.** Requires no patch and matches what the wizard will do for r6.
The cost is that the startup file no longer records the credential the device
ends up with, so "survives redeploy" becomes "survives redeploy, then needs a
rotation" — a weaker property, and one somebody has to remember.

I lean to **(a)** for the reason given: it keeps the file and the device in
agreement, which is what a source of truth is for. (b) is the fallback if the
probe shows vrnetlab depends on injecting that account.

---

## Stage C — evaluating fix (a) on the probe

Deploy only after stages A and B are destroyed and `clab-bootstrap-probe` is
gone. One node, same isolated network.

### C-pre. Build the patched launch script

The patch is **copied** and then edited, never edited in place. The patcher
refuses a path under `~/labs/lab`.

```bash
cd ~/labs/bootstrap-probe
cp ~/labs/lab/patches/c8000v-launch.py patches/c8000v-launch-userskip.py

# Confirm the starting point is rcn-lab1's own patch, unmodified.
diff ~/labs/lab/patches/c8000v-launch.py patches/c8000v-launch-userskip.py \
  && echo "identical to production patch"

# Show the diff. Writes nothing.
python3 patches/patch-skip-injected-user.py patches/c8000v-launch-userskip.py

# Apply it.
python3 patches/patch-skip-injected-user.py patches/c8000v-launch-userskip.py --write

# The whole divergence from stock, in one place: smp="2" plus the user skip.
diff ~/labs/lab/patches/c8000v-launch.py patches/c8000v-launch-userskip.py
```

The patcher **refuses** rather than guessing if the file is not what stage B
measured: no `import re` / `import logging`, no injected
`username … privilege 15 password …` line, not exactly one
`cfg = self.gen_bootstrap_config() + startup_cfg`, or already patched. A
refusal means the reading this fix rests on is stale — report it rather than
forcing the edit.

The functional change is **two lines** at the concatenation site; the rest of
the diff is the helper and its comment.

### C0. Does the patch break the boot at all?

The startup config here defines `admin` with the **password** form and the
value `admin` — the credential vrnetlab was given. So the injection is
skipped, but the device still ends up with the credential vrnetlab knows.

```bash
cp configs/bp-c8k.cfg configs/bp-c8k-stage-c.cfg
containerlab deploy -t nmas-userskip-probe.clab.yml

c=clab-nmas-userskip-probe-bp-c8k-c
time docker logs -f $c 2>&1 | grep -m1 "Startup complete"   # expect < 15 min
docker logs $c 2>&1 | grep -i "not injecting"               # the patch speaking
docker inspect --format '{{.State.Health.Status}}' $c       # expect: healthy
```

| C0 outcome | meaning |
|---|---|
| Startup complete, healthy | the patch mechanism is sound — go to C1 |
| stalls or unhealthy | **(a) is dead regardless of credentials.** Report the last 40 log lines and fall back to (b); C1 would tell us nothing more |

Then regenerate the type-9 hash C1 needs (stage A's node is gone):

```bash
ssh -o StrictHostKeyChecking=no admin@172.30.30.41
  conf t
  username probehash privilege 15 algorithm-type scrypt secret ProbeSecretValue1
  do show run | include ^username probehash
  no username probehash
  end
```

Copy the `$9$…` hash into the template exactly as printed, then tear down:

```bash
sed "s|@@HASH@@|<the $9$ hash>|" configs/bp-c8k-secret9.cfg.template \
  > configs/bp-c8k-secret9.cfg
grep -c '\$9\$' configs/bp-c8k-secret9.cfg        # expect 1
containerlab destroy -t nmas-userskip-probe.clab.yml --cleanup
```

If `configs/bp-c8k-secret9.cfg` from stage B still exists, skip the
regeneration and use it — then `diff` proves C1 booted the same bytes stage B
did.

### C1. The real test

```bash
cp configs/bp-c8k-secret9.cfg configs/bp-c8k-stage-c.cfg
diff configs/bp-c8k-secret9.cfg configs/bp-c8k-stage-c.cfg && echo "same config"
containerlab deploy -t nmas-userskip-probe.clab.yml

c=clab-nmas-userskip-probe-bp-c8k-c
time docker logs -f $c 2>&1 | grep -m1 "Startup complete"
```

Then, all five pass criteria:

```bash
# 1. no CVAC rejection for the username line
docker logs $c 2>&1 | grep -i "CVAC-4-CLI_FAILURE" || echo "PASS: no CLI failure"

# 2. the skip actually fired
docker logs $c 2>&1 | grep -i "not injecting"

# 3. running config carries secret 9
ssh -o StrictHostKeyChecking=no admin@172.30.30.41 \
  "show running-config | include ^username admin"
#    expect: username admin privilege 15 secret 9 $9$...
#    NOT:    username admin privilege 15 password 0 admin

# 4. the file's credential is accepted and vrnetlab's is refused
#    (deliberately two separate attempts, not one inference)
sshpass -p 'ProbeSecretValue1' ssh -o StrictHostKeyChecking=no \
  admin@172.30.30.41 "show version | include uptime" && echo "PASS: file cred accepted"
sshpass -p 'admin' ssh -o StrictHostKeyChecking=no -o NumberOfPasswordPrompts=1 \
  admin@172.30.30.41 "show version" && echo "FAIL: admin still works" \
  || echo "PASS: admin refused"

# 5. the container is healthy, not merely running
docker inspect --format '{{.State.Health.Status}}' $c
```

**All five must pass.** Criterion 5 is separate from criterion 1 on purpose:
stage B reached `Startup complete` *and* was healthy while holding the wrong
credential, so neither one alone says the node is what its file describes.

### If C1 stalls

C0 passing and C1 stalling is the signature of **vrnetlab needing the account
it injects** — it can reach the console while the credential is still `admin`
and not once the config has changed it. Report:

```bash
docker logs $c 2>&1 | tail -60        # where it stops, verbatim
docker inspect --format '{{.State.Health.Status}}' $c
```

The line it stops on is the finding. A stall at a login prompt after the
config is applied says vrnetlab logs back in; a stall before it says something
else, and the two lead to different fixes.

Then fall back to **(b)**: the startup file carries the password form and
`set_credential` rotates after boot. Note what (b) costs, so it is chosen
knowingly rather than by exhaustion — the startup file stops recording the
credential the device ends up with, so "survives redeploy" weakens to
"survives redeploy, then needs a rotation somebody has to remember".

### C2. Destroy

```bash
containerlab destroy -t nmas-userskip-probe.clab.yml --cleanup
docker network rm clab-bootstrap-probe 2>/dev/null || true
rm -f configs/bp-c8k-stage-c.cfg configs/bp-c8k-secret9.cfg   # generated hashes
```

### What a C1 pass does and does not license

A pass means fix (a) works **on the probe**, on one node, on this image. It
does **not** lift the redeploy ban by itself. Lifting it needs, in order:

1. the patched script adopted into `~/labs/lab/patches/` — the file r1–r5
   already bind, so every router picks it up;
2. the persistence chain's applicability check in place (below), so the next
   rotation cannot recreate this silently;
3. a rollback path if a redeploy still goes wrong — the five routers'
   current credentials recorded somewhere that survives them being
   unreachable.

---

## Stage D2 — the switches are unproven too

Asked before the production redeploy was scheduled, and the repository
answered it: **no vIOS has ever booted a `secret 9` line.**

| stage | node | username line | result |
|---|---|---|---|
| A | `bp-vios` | `secret 0 admin` (**plaintext**) | booted |
| B | `bp-c8k-b` | `secret 9 $9$…` | refused — hazard confirmed |
| C | `bp-c8k-c` | `secret 9 $9$…` | applied — fix proven |

Every `secret 9` boot was a **C8000v**. The switches were rotated the same
day and their startup files carry the same shape, and that shape has never
been fed back to the platform that emits it.

Two properties are untested, and only the first is shared with the routers:

1. **Consumption.** Rotation sends `algorithm-type scrypt secret <plaintext>`
   — the *device* computes the hash. `clab-sync` harvests
   `show running-config`, which writes `secret 9 $9$salt$hash`. The device
   emits a form it has never been asked to read back at boot. That was equally
   true of the routers until stage B measured it.
2. **Console replay.** vrnetlab *types* a vIOS startup config into the console
   line by line; the routers' is loaded as a file. Stages B and C therefore
   prove nothing about this path — and it is the path where a comment hung a
   boot.

`nmas-vios-d2.clab.yml` and `configs/bp-vios-secret9.cfg.template` run it by
stage B's method on the other platform: boot the known-good shape, generate a
throwaway hash on the device, destroy, refill, reboot.

The template carries **no prose comments**. A first draft had nineteen, which
on a console-replayed platform is nineteen lines typed into a console for no
reason — the shape that hung run 2. `test_bootstrap_config.py` now fails on a
prose comment in any `vios` config here.

**Without D2, the production redeploy is the first test of four switches at
once.**

---

## Stage D2 result: the switches are cleared (2026-09-22)

| observation | value |
|---|---|
| hash generation | vIOS produces `secret 9` from `algorithm-type scrypt` — confirming what the rotation stored |
| Startup complete | 2m03s |
| boot log | no errors, rejections or CLI failures |
| `username admin` | `privilege 15 secret 9 $9$…` — applied |
| `transport input ssh` | present — the **last** section of the file |
| Gi0/0 | up, DHCP address — also after the username line |
| the file's credential | **accepted** over SSH |
| `admin` | **refused** |

Both the `transport input` and Gi0/0 checks sit *after* the username line, so
the console replay did not stall. That was the point of checking something
after the line under test: a stalled replay looks like a slow boot.

### Two findings the run produced that the run was not looking for

**1. The refusal check could not fail.** The first login attempts died at
**key exchange** — a modern OpenSSH against this 2018 image — and
`sshpass ... || echo PASS` printed PASS for that reason. It would print PASS
with the device powered off. The production checklist carried the identical
line, where it would have reported "the routers refuse `admin`" while every
router sat on `admin/admin` and unreachable.

`scripts/nmas-check-credential` replaces it: three verdicts (ACCEPTED /
REFUSED / **INCONCLUSIVE**) from `verify_new_credential()`, which already
separates a device verdict from a transport fault — and it connects **the way
NMAS does**, through Netmiko, rather than through the shell's `ssh`. The claim
is "NMAS can log in"; the shell is a different client, and that difference is
what produced the false pass.

**2. A vIOS silently reloaded.** A CPU exception (PnP Agent Discovery,
SIGBUS) during the first boot; the container stayed healthy, `docker logs`
said nothing, and only `show version | include uptime` revealed it. The
post-redeploy checklist gains a per-device uptime check: a node that reloaded
after its config was applied is a node whose running config may not be what
the log says was applied, and `Startup complete` will have been printed by
the first boot.

### Free reading for stage D

`crypto key generate rsa modulus 2048` took **3 seconds** on vIOS, typed
interactively. That is not a boot-time console replay, so it does not close
stage D — but it makes a stall on that line unlikely.

---

## What the persistence chain must check instead

`verify_startup_file()` currently greps the startup file for the new hash.
That is a **presence** check, and the hazard above is precisely a case where
presence is satisfied and the property is not: the hash is in the file and the
file does not apply.

The replacement is an **applicability** check, and it can be done without
redeploying production:

1. **A static, platform-aware rule, on every rotation.** The chain knows the
   platform and can know what that platform's launch path injects. On a
   C8000v, a `username <vrnetlab-user> … secret …` line in a startup file is
   unappliable, because a password line for that user lands first. That is
   cheap, runs every time, and would have caught this at the moment the first
   router rotated.
2. **A dynamic proof, once per platform, on the probe.** Boot the actual
   startup file on a throwaway node and confirm the credential the file
   describes is the credential the device answers on. Recorded as evidence
   with its capture, exactly like the bootstrap profile — not run per
   rotation, because it costs five minutes and a node.

The static rule is the one that belongs in the persistence chain. The dynamic
proof is what establishes the rule is right, and is re-run when an image or a
launch script changes — which is the only time the answer can move.

> A presence check asks whether the artefact contains the right bytes. An
> applicability check asks whether the machine that reads it will end up in
> the state those bytes describe. They differ exactly when something else
> writes to the same place first, which is the case nobody thinks of.

---

## Stage D — does key generation survive a console replay?

**Not yet run.** This is the last Stage 4 prerequisite.

### The unmeasured intersection

`cisco_ios` is the only platform in **both** `GENERATES_SSH_KEY` and
`CONSOLE_REPLAYED` (`modules/nsot/bootstrap_config.py`). vrnetlab types a
vIOS startup config into the console line by line and waits for a prompt
after each; key generation takes real time and prints its own progress.
Nothing has measured what happens when those two meet.

D2 measured `crypto key generate rsa modulus 2048` at **3 seconds**, typed
**interactively**. That makes a stall unlikely and **it is not the same
test**: an interactive session waits for you, a replay waits for a prompt
pattern with a timeout.

### What a stall costs, precisely

The generator emits **25 lines** for `cisco_ios` and the crypto line is
**line 17**. Eight lines come after it, and this is all of them:

```
ip ssh version 2
line vty 0 4
 logging synchronous
 login local
 transport input ssh
end
```

So a stall does **not** produce a device that looks broken. It produces one
that reaches `Startup complete`, answers ping, has a hostname and a
management address — **and cannot be reached over SSH**, because the vty
block never landed.

That is stage B's shape exactly: a startup file that reads correctly and does
not fully apply. It is also why "did it boot?" is not the check.

### Two nodes, because the control is not optional

`bp-vios-d3` carries what the generator emits. **`bp-vios-d3neg` carries the
same file truncated after the crypto line** — the state a stall would leave
behind — and **every check below must fail on it.** Five can't-fail controls
have been found in this project; this one ships with its control attached.

### Running it

**1. Render the configs from the generator.** Not by hand: a hand-written
fixture measures the fixture. Neither file is committed; both carry a
credential and both are gitignored.

```bash
cd ~/python/Agentic_NMAS
python scripts/nmas-render-d3-probe --secret '<throwaway password>'
```

It prints the crypto line number and the lines that come after it. Confirm
the count matches what is written above; if the generator has changed, this
runbook is describing a different file.

**2. Deploy the probe lab.** Destroy earlier probe labs first so nothing
contends for `172.30.30.0/24`.

```bash
cd ~/labs/bootstrap-probe          # wherever the probe clab files live
sudo containerlab deploy -t nmas-vios-d3.clab.yml
```

**3. Watch the replay on the good node.** This is the measurement; the checks
afterwards only confirm what it shows.

```bash
docker logs -f clab-nmas-vios-d3-bp-vios-d3 2>&1 | ts
```

Record:
* the timestamp of the line containing `crypto key generate rsa`
* the timestamp of the **next** line the replay sends (`ip ssh version 2`)
* whether `Startup complete` is reached, and when
* any `% ` error, any timeout, any prompt-wait warning

**The gap between those first two timestamps is the whole answer.** D2's
interactive figure was 3 seconds.

**4. Check the good node — every one of these must pass.**

```bash
N=clab-nmas-vios-d3-bp-vios-d3
docker exec $N bash -lc 'echo ok'   # container up

# a) the key exists
ssh admin@172.30.30.53 'show crypto key mypubkey rsa | include Key name|Key Data' 

# b) THE LINES AFTER THE CRYPTO LINE LANDED -- the actual property
ssh admin@172.30.30.53 'show running-config | include ^ip ssh version 2'
ssh admin@172.30.30.53 'show running-config | section line vty'

# c) SSH works at all, which is (b) observed from the outside
ssh admin@172.30.30.53 'show version | include uptime'
```

If (c) works you have already proved (b) — you could not have logged in
without the vty block. Run both anyway: (b) names *which* line is missing
when it fails, and (c) only says "no".

**5. Check the negative node — every one of these must FAIL.**

```bash
ssh admin@172.30.30.54 'show version'      # expected: connection refused
```

A refused connection here is the control passing. **If SSH to `.54` works,
stop**: the truncated file applied something it should not have, and the
checks above cannot distinguish a stall from a success.

Distinguish *refused* from *timed out* from *auth failed*, for the reason
stage D2 recorded — a check that cannot tell a transport failure from an auth
failure is a check that cannot fail. `scripts/nmas-check-credential` gives
three-valued answers and is the right tool:

```bash
python scripts/nmas-check-credential --host 172.30.30.54 --username admin
```

**6. Per-device uptime**, per the D2 finding: a vIOS can take a CPU exception
and silently reload, and `Startup complete` will have been printed by the
first boot.

```bash
ssh admin@172.30.30.53 'show version | include uptime'
```

**7. Destroy and clean up.**

```bash
sudo containerlab destroy -t nmas-vios-d3.clab.yml --cleanup
rm -f docs/bootstrap-probe/configs/bp-vios-d3.cfg \
      docs/bootstrap-probe/configs/bp-vios-d3neg.cfg
```

### What a pass licenses, and what it does not

A pass says: **on this image, at this modulus, key generation does not stall a
console replay, and the lines after it land.** It says nothing about a larger
modulus, a different vIOS image, or a slower host — and the margin is what
matters, so **record the measured gap**, not just "it worked".

A **fail** does not block Stage 4. It moves the key generation: either out of
the startup file and into a post-boot step over the console, or ahead of the
vty block so a stall costs nothing that matters. The point of measuring first
is that either answer is cheap now and expensive after r6 is onboarded.
