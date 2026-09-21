# Measuring the bootstrap profile

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
