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

---

## Why a separate topology

`rcn-lab1` is the production lab. Its nodes are configured, which makes them
useless for this measurement, and it is the thing the whole project manages,
which makes experimenting in it a bad trade.

`nmas-bootstrap-probe.clab.yml` shares nothing with it:

| | rcn-lab1 | the probe |
|---|---|---|
| lab name | `rcn-lab1` | `nmas-bootstrap-probe` |
| docker network | default `clab` | `clab-bootstrap-probe` |
| subnet | 172.20.20.0/24 | 172.30.30.0/24 |
| startup configs | per node | **none** |
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

Run on `10.0.0.210`. Steps 1 and 5 are the only ones that change anything, and
step 5 undoes step 1.

### 1. Deploy

```bash
mkdir -p ~/labs/bootstrap-probe/captures
# copy nmas-bootstrap-probe.clab.yml into ~/labs/bootstrap-probe/
cd ~/labs/bootstrap-probe
containerlab deploy -t nmas-bootstrap-probe.clab.yml
```

The C8000v takes several minutes to boot. Wait for both to answer:

```bash
until ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 admin@172.30.30.11 \
      'show version | include uptime' 2>/dev/null; do sleep 20; done
until ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 admin@172.30.30.21 \
      'show version | include uptime' 2>/dev/null; do sleep 20; done
```

### 2. Capture

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

### 3. Hand the captures back

```bash
# from the NMAS
scp dmarchak@10.0.0.210:~/labs/bootstrap-probe/captures/'*' /tmp/bootstrap/
```

They land in the repository as fixtures, with their provenance, at
`tests/fixtures/bootstrap/<platform>.cfg`. The profile is derived from them in
code and tested against them, so a future image change is a failing test
rather than a wrong answer.

### 4. Verify the captures are what they claim

Before trusting them: each should contain a hostname, a management interface,
**no routing process**, and **no addressed data interface**. If either capture
shows a routing process, the node is not fresh and the profile must not be
built from it.

### 5. Destroy

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
