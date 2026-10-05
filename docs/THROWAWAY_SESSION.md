# The throwaway session: one C8000v, from first DHCP request to teardown

One sitting, one throwaway device, its own lab, its own list. **Nothing touches the fleet**
(r1-r6, s1-s4). It replaces NSOT_STAGE7_PLAN's "Session 2" and the ZTP measurements that plan's
section 16 left to the operator, in one order:

| Part | What it measures | Time |
|---|---|---|
| 0 | setup: stage the lab, check nothing collides, census baseline, the list | 25 min |
| 1 | ZTP discovery: every DHCP request for 60 minutes, its options, whether it gives up | 75 min |
| 2 | the Pick: reservation written, how long until the device takes its boot file | 15 min |
| 3 | onboarding phase 2 (Verify), the Devices list redrawn, template approval, seed | 30 min |
| 4 | the break-glass export retire needs | 10 min |
| 5 | C178's hold question, then C117's loop: a deploy that fails verify and rolls back | 75 min |
| 6 | retry and revert (A2) | 35 min |
| 7 | a restore that sends a line | 25 min |
| 8 | retire (A3) | 20 min |
| 9 | the guestshell serial probe | 20 min |
| 10 | cleanup, the census compare | 30 min |

**About 6 hours in all, about 1 hour of it waiting.** Part 1 is the longest wait, and the
session cannot start later than 6 h 30 min before the nightly backup (08:30 UTC, 02:30 your
time). A start between 10:00 and 01:30 UTC (04:00 to 19:30 your time) clears it. The natural
pause is after Part 4: the device is onboarded and nothing is in flight.

**Times:** write every time as UTC (`date -u +%FT%TZ`). A device's own timestamps are not used
for anything (its clock is not trusted); an event's time is when you saw it, or its syslog
receive time on the device's History tab.

## The values

| What | Value | Where it is checked |
|---|---|---|
| list | `throwaway` | Part 0, step 6 |
| device | `tw-ztp-a`, C8000v 17.06.01a, configless boot | the topology |
| MAC and address on Gi2 | `aa:bb:cc:00:02:60` → `10.255.0.60/24` | Part 0, steps 3 and 4 |
| BGP peer | `tw-frr` (FRR 10.2.1), `10.255.0.35`, loopback `10.255.98.1`, AS 65098 | the topology |
| the throwaway's Loopback1 | `10.255.99.1/32`, AS 65099 | Part 5 |
| lab | `nmas-throwaway`, `docs/bootstrap-probe/nmas-throwaway.clab.yml`, on the lab host in `<home>/labs/throwaway/` | |
| its management subnet | `172.30.90.0/24`, network `clab-throwaway-probe` | Part 0, step 3 |
| bridge ports on `br-mgmt` | `tw-mgmt`, `twfrr-mgmt` | Part 0, step 3 |
| the ZTP segment | lab host `br-mgmt`; NMAS host `enp6s19` (`10.255.0.10/24`), Kea subnet 255 | Part 0, step 4 |
| containers | `clab-nmas-throwaway-tw-ztp-a`, `clab-nmas-throwaway-tw-frr` | |

Measured free on 2026-10-05, read-only:
- **Kea:** `.60`, `.35` and both MACs are in no line of Kea's configuration, and the NMAS
  fragment holds 0 entries.
- **The lab host:** `172.30.90.0/24` is no docker network there, and `br-mgmt` holds only
  `enp6s19`, `s3-mgmt` and `r6-mgmt`.
- **The fleet's intent and goldens:** no golden or intent file of the Default list names
  `10.255.98.x`, `10.255.99.x`, 65098 or 65099.

The subnet is declared by the topology file itself. `tests/test_probe_topologies.py` refuses
another probe taking it, under another name or as a second subnet for this name. It is
deliberately NOT in `RESERVED_MGMT_SUBNETS`: that list is for subnets taken OUTSIDE the
repository, and that test fails any topology here whose subnet is on it.

**One fact governs the whole session.** The configless launch script removes the node's overlay
at every CONTAINER start. So `docker restart`, or a redeploy, returns `tw-ztp-a` to no
configuration at all. An IOS `reload` inside the running container keeps what it saved. After
Part 2, never restart the container.

**What is whose.** Every command below is yours (root on the lab host, and the NMAS host). The
tool does the rest:
- the Kea reservation (Create);
- the TFTP answer (the responder);
- NetBox (phase 2);
- seed, deploy, rollback, retry, revert, restore and retire.

## Part 0: setup (25 min)

**0.1 The current main is deployed.** The NMAS host runs a commit CI passed (`nmas-deploy --wait`
if not).

**0.2 Stage the lab (lab host).**

    mkdir -p <home>/labs/throwaway/patches <home>/labs/throwaway/configs/tw-frr
    cp <home>/labs/ztp-a/patches/c8000v-launch-configless.py <home>/labs/throwaway/patches/
    sha256sum <home>/labs/throwaway/patches/c8000v-launch-configless.py | cut -c1-16

Expect `972a0f72f1ee5847` (the patched script P6_ZTP_PROBE.md measured). Then, from the laptop's
checkout of this commit:

    T=$(scripts/nmas-host clab --target)
    scp docs/bootstrap-probe/nmas-throwaway.clab.yml "$T":labs/throwaway/
    scp docs/bootstrap-probe/configs/tw-frr/daemons docs/bootstrap-probe/configs/tw-frr/frr.conf "$T":labs/throwaway/configs/tw-frr/

**0.3 Nothing collides (lab host).**

    docker network ls --format '{{.Name}}' | xargs -n1 docker network inspect -f '{{.Name}} {{range .IPAM.Config}}{{.Subnet}} {{end}}'
    ip -br link show master br-mgmt

Expect no `172.30.90.0/24`, and `br-mgmt` holding `enp6s19`, `s3-mgmt@…` and `r6-mgmt@…` only.

**0.4 Kea knows neither address (NMAS host).** All four must print 0:

    grep -c '10.255.0.60' /etc/kea/kea-dhcp4.conf
    sudo grep -c 'aa:bb:cc:00:02:60\|10.255.0.60' /var/lib/kea/kea-leases4.csv
    grep -c '10.255.0.60\|10.255.0.35' /etc/kea/nmas/reservations-255.json
    sudo grep -c '10.255.0.35' /var/lib/kea/kea-leases4.csv

Then, in v2 Needs attention, **What was checked** shows `ztp-posture:subnet-255` as ok (the
responder and the fragment are in place).

**0.5 The census baseline, BEFORE anything writes (NMAS host).** It cannot be taken afterwards.

    cd <home>/python/Agentic_NMAS && PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-netbox-census --out /tmp/census-throwaway.json && test -s /tmp/census-throwaway.json && echo "baseline present"

In NetBox, search for `tw-ztp-a` and for `10.255.0.60`: both find nothing.

**0.6 The list, and NetBox writes (today's page).**
1. Device List bar: **+ New List**, named `throwaway`. Select it; the dropdown reads
   `throwaway (0 devices)`.
2. Settings › Integrations: **Allow writes to NetBox** is on. Leave it on.

**STOP 0. Paste:** the hash line, the two lab-host listings, the four zeros, and "baseline
present".

## Part 1: ZTP discovery, 60 minutes (75 min)

The node boots with no configuration and no boot file is offered: subnet 255 has no pool, so
Kea answers nothing until Part 2's reservation. This measures what an unpicked device does. A
"discovery range" (a lease with no boot file) is the host step section 16 says follows from
these numbers. It does not exist yet, and this run does not create it.

**1.1 The observers, before the boot (lab host, two terminals).**

    sudo tcpdump -ni br-mgmt -e -w /tmp/tw-dhcp.pcap ether host aa:bb:cc:00:02:60
    sudo tcpdump -ni br-mgmt -e -l -tttt -vvv -s0 'ether host aa:bb:cc:00:02:60 and (udp port 67 or udp port 68 or udp port 69)'

The second terminal is the live view: each DISCOVER with its absolute time and every option
decoded.

**1.2 Deploy (lab host).**

    date -u +%FT%TZ
    cd <home>/labs/throwaway && sudo containerlab deploy -t nmas-throwaway.clab.yml
    docker exec clab-nmas-throwaway-tw-ztp-a sha256sum /launch.py | cut -c1-16
    docker logs clab-nmas-throwaway-tw-ztp-a 2>&1 | grep -E "CONFIGLESS|Creating overlay disk image"

Expect `972a0f72f1ee5847`, then three lines in order:
1. `CONFIGLESS: booting the base disk …17.06.01a.qcow2`;
2. `CONFIGLESS: removing …-overlay.qcow2`, or `…nothing to remove`;
3. `Creating overlay disk image: …-overlay.qcow2`, with ONE "-overlay".

`-overlay-overlay` means the install overlay booted: destroy and stop. Then check the peer:

    docker exec clab-nmas-throwaway-tw-frr vtysh -c 'show bgp summary'

Expect neighbour `10.255.99.1` in `Active` or `Connect` (it has no peer yet).

**1.3 The console, read-only (lab host, a third terminal).** Watch it through a reader that
SENDS NOTHING, never an interactive telnet:

    docker exec clab-nmas-throwaway-tw-ztp-a python3 -c 'import socket, sys; s = socket.create_connection(("127.0.0.1", 5000)); [sys.stdout.buffer.write(d) or sys.stdout.flush() for d in iter(lambda: s.recv(4096), b"")]'

No `-it`: the container gets no terminal, so no keystroke can reach the device, and the
reader never answers the console's telnet negotiation. Stop it with Ctrl-C. The output may
carry a few raw negotiation bytes; ignore them.

**Why not telnet (measured in this session, Part 1, 2026-10-05):** with `telnet 127.0.0.1 5000`
attached and nothing typed, the setup dialog printed `% Please answer 'yes' or 'no'` again
and again, once with a stray `}`. So the device RECEIVED input nobody typed: the telnet
client's negotiation bytes, or vrnetlab's launch script still connected, which one is not
known. Autoinstall warns that any console input terminates it. DHCP discovery continued
regardless that time. The operator then disconnected the telnet and switched to the read-only
reader (the time is not recorded here), and discovery continued throughout. Observing must
never be able to end what is observed, so the reader is the way to watch a console during
discovery.

**Type nothing for the whole of Part 1**: not RETURN, not `en`, not an answer to the dialog.
Any input ends discovery (`PnP Discovery stopped (Config Wizard)`, measured in M4).

**1.4 Wait 60 minutes from the FIRST DISCOVER** the live view shows. Booting takes several
minutes first. Note the first DISCOVER's time. While waiting, watch the console for:
- the setup dialog (`Would you like to enter the initial configuration dialog?`);
- `%PNP`, `AUTOINSTALL` or DHCP lines.

**1.5 Read the hour off (lab host, after 60 minutes; leave both captures running).**

    sudo tcpdump -nr /tmp/tw-dhcp.pcap -tt 'udp src port 68' 2>/dev/null | awk '{print $1}' > /tmp/tw-discover-times.txt
    wc -l < /tmp/tw-discover-times.txt
    date -u -d @"$(head -1 /tmp/tw-discover-times.txt)" +%FT%TZ; date -u -d @"$(tail -1 /tmp/tw-discover-times.txt)" +%FT%TZ
    awk 'NR>1{printf "%d\n", $1-p} {p=$1}' /tmp/tw-discover-times.txt | sort -n | uniq -c
    awk 'NR>1{printf "%s %d\n", NR, $1-p} {p=$1}' /tmp/tw-discover-times.txt | tail -15
    sudo tcpdump -nr /tmp/tw-dhcp.pcap -vvv -s0 -c 1 'udp src port 68'

What each line answers:
- the count;
- the first and last request, in UTC;
- the interval histogram (do the intervals grow?);
- the last 15 intervals (did it stop, or is it still asking?);
- the first DISCOVER in full: its options 60 (vendor class), 61 (client-id), 124 and 125, and
  whether any of them carries a serial.

**STOP 1. Paste:**
- the six outputs above;
- the console's last screen, as text;
- your answer, from the console and the times: is it still asking, or did it stop, and if it
  stopped, did it fall back to the setup dialog or sit at an empty configuration?

## Part 2: the Pick (15 min)

The "Pick" (board L, 15.7) is not built yet. Today it is the onboarding wizard's Create with
the source ZTP: it writes exactly the reservation a Pick will write (address, option 12, the
TFTP server and `tw-ztp-a.cfg`). So Part 2 is also the first half of onboarding.

**2.1 Create (today's page, list `throwaway` selected).** Add device:

| Field | Value |
|---|---|
| Target list | `throwaway` |
| Name | `tw-ztp-a` |
| Platform | C8000v (IOS-XE) |
| Role | router |
| Address from | ZTP (the tool reserves it and serves the config) |
| Management address and mask | `10.255.0.60`, `255.255.255.0` |
| MAC address | `aa:bb:cc:00:02:60` |
| Management interface | `GigabitEthernet2` |
| Gateway | blank (the NMAS host is on the same segment) |
| Containerlab interface | blank (the throwaway is in no clab manifest) |

The review says it WRITES the Kea reservation, and that the device fetches `tw-ztp-a.cfg` by
TFTP from `10.255.0.10`. Write down `date -u +%FT%TZ` as you press **Create**: that is the Pick
time. The result reads "Partly done" and PENDING, and the pending row reads
`ZTP: reserved …; no lease yet`.

**2.2 The reservation is live (NMAS host).**

    sudo python3 <home>/python/Agentic_NMAS/docs/bootstrap-probe/kea-m5.py show

Expect one entry for `aa:bb:cc:00:02:60` with hostname `tw-ztp-a`, `tftp-server-name` and
`boot-file-name` `tw-ztp-a.cfg`, and no route (3) or resolver (6).

**2.3 Watch the live view.** The next DISCOVER now gets an OFFER and an ACK carrying 66 and 67,
and then comes `RRQ "tw-ztp-a.cfg"` (TFTP fetches retry about every 8 s; measured in M4).
Also run `journalctl -u nmas-ztp-responder -f` on the NMAS host. Note:
- the time of the first OFFER;
- the time of the first RRQ;
- the console line that says the configuration applied.

**If no DISCOVER arrives within 15 minutes of the Pick,** the device had stopped asking. That
is a result: record it. Then re-trigger it with the lab's power cycle, which also restores
the configless state:

    <home>/python/Agentic_NMAS/scripts/nmas-planned-restart throwaway tw-ztp-a --minutes 20 --why "throwaway ZTP re-trigger after discovery stopped" --by <operator>
    docker restart clab-nmas-throwaway-tw-ztp-a

Then note the time of its first DISCOVER after the restart, and its OFFER and RRQ.

**STOP 2. Paste:**
- the Pick time;
- the first OFFER, the first RRQ and the "applied" times;
- `kea-m5.py show`;
- the responder's journal lines;
- if the device had stopped: that it had, and the restart's numbers.

## Part 3: onboarding finished, template, seed (30 min)

**3.1 Verify (today's page, the pending row of `tw-ztp-a`).** Before pressing it, open v2
**Devices** in a second tab and leave it open. Then press **Verify** (preview, then confirm).
Phase 2:
- rotates the credential;
- records NetBox (writes on);
- captures the first golden.

The row moves to "Finished recently". **The v2 Devices tab shows `tw-ztp-a` without a reload**
(7.0's acceptance 5); if it does not, say so.

**3.2 The template (today's page, Templates, list `throwaway`).** Approve
`cisco_iosxe/base.j2` with the fingerprint shown. It needs the golden 3.1 recorded; approval
does not carry between lists.

**3.3 Seed (v2, `tw-ztp-a`'s page).** Actions › **Seed intent…**:
- the document lists what becomes intent;
- unmodelled lines are named;
- confirm.

One commit, `Source: seed`. The Intent tab now shows the device's intent.

**STOP 3. Paste:**
- the Verify result's headline;
- whether the Devices tab redrew by itself;
- the approval result;
- the seed result's headline and its unmodelled lines.

## Part 4: the break-glass export (10 min)

Retire (Part 8) refuses unless the list's NEWEST export holds the device's CURRENT credential,
and 3.1 rotated it. In v2 Source of truth › **Credentials** (`/v2/credentials?list=throwaway`),
export the record (preview, passphrase, export). Keep the file as you keep the fleet's, never
in the repository.

**STOP 4. Paste:** the export's result line (it names the devices and the digest count, never a
value). This is the natural pause.

## Part 5: C178's hold question, then C117's loop (75 min)

**5.1 Deploy 1: the peer comes up.** On `tw-ztp-a`'s v2 page, Intent tab, **Edit intent…**,
add the following, which must render as exactly these lines:

    interface Loopback1
     ip address 10.255.99.1 255.255.255.255
    ip route 10.255.98.1 255.255.255.255 10.255.0.35
    router bgp 65099
     bgp router-id 10.255.99.1
     neighbor 10.255.98.1 remote-as 65098
     neighbor 10.255.98.1 ebgp-multihop 2
     neighbor 10.255.98.1 update-source Loopback1

Commit. Then **Plan a deploy…**: the program is those eight lines and nothing else (the merge
adds only what is missing). Confirm. Verify waits for BGP's hold time (C178), so the deploy
takes up to about 4 minutes. Expect it to pass, with BGP 0 → 1 neighbour. Then:

    docker exec clab-nmas-throwaway-tw-frr vtysh -c 'show bgp summary'

Expect `10.255.99.1` Established.

**5.2 C178's question: does a silent path hold the session until hold expiry?** Nothing is
deployed here; the break is on the PEER. From now on, every time you note is UTC.

    date -u +%FT%TZ; docker exec clab-nmas-throwaway-tw-frr ip route replace blackhole 10.255.99.1/32

From that moment, the peer's packets to Loopback1 are dropped silently, and IOS sees only
silence. On `tw-ztp-a`'s console (typing is fine now), run `show bgp ipv4 unicast summary`
every 20 s. Note:
- when the neighbour leaves Established;
- the `%BGP-5-ADJCHANGE … Down` line's receive time, on the device's History tab;
- the reason it gives (`hold time expired` or otherwise).

Then heal it:

    date -u +%FT%TZ; docker exec clab-nmas-throwaway-tw-frr ip route replace 10.255.99.1/32 via 10.255.0.60

Wait until it is Established again. **What it decides:**
- Down within seconds: IOS resets on something it can see.
- Down at about 180 s: exactly C178's case. A verify reading at 10 s would have passed, and the
  hold watch exists for this.

**5.3 Deploy 2: the break that rolls back (C117).** Edit intent again: add `shutdown` under
`interface Loopback1`. Commit. **Plan a deploy…**:
- the program is `interface Loopback1` / ` shutdown`;
- the line is dangerous, so authorise it with a reason (at least three words, for example
  "C117 rollback test on the throwaway");
- confirm.

Expect:
- verify FAILS (Loopback1 down; the session drops);
- the rollback sends `no shutdown`;
- the per-device rollback reads **`restored`**, from C112's read-back over a fresh connection;
- the result is red, never green over the failure;
- the receipt is written;
- BGP comes back (`show bgp summary` on the peer).

**STOP 5. Paste:**
- deploy 1's program and result;
- 5.2's times: blackhole, Established lost, ADJCHANGE receive time with its reason, heal,
  Established again;
- deploy 2's result as drawn: verify's failing check, the rollback state, the receipt line.

## Part 6: retry and revert, A2 (35 min)

A rollback BLOCK now stands. Actions offers **Revert intent…** and **Retry rolled-back
change…**; before 5.3, both were greyed with their reason.

**6.1 Retry.** Actions › **Retry rolled-back change…**, with a reason (for example "retrying
once to measure the block"). Nothing is sent. Expect:
- the block is lifted;
- **Plan a deploy…** now offers `shutdown` again: read the program, and do NOT confirm it.

**6.2 Re-break.** Confirm that same plan this time. Expect it to fail and roll back to
`restored` again, with the block standing again.

**6.3 Revert.** Actions › **Revert intent…**:
- choose the commit that added `shutdown`;
- confirm: one forward commit, `Source: revert`, and nothing sent to the device.

Expect:
- the block is lifted because it is MEASURED gone (a fresh plan would no longer send the failed
  line), never because a revert happened;
- the Actions menu greys Revert and Retry again, saying why;
- **Plan a deploy…** has nothing to send.

**STOP 6. Paste:** each step's result headline, the plan 6.1 offered, and the menu's reason
after 6.3.

## Part 7: a restore that sends a line (25 min)

A restore re-applies what an earlier golden had and today's golden lacks. It is additive, and
it never compares the device itself. So, first a hand change, and the golden records it.

**7.1 The hand change (console).**

    conf t
     no ip route 10.255.98.1 255.255.255.255 10.255.0.35
     end

The BGP session will drop within the hold time. Note the time.

**7.2 Capture (v2).** Actions › **Capture**. The new golden lacks the static route.

**7.3 Restore (v2).** Actions › **Restore from…**:
- choose the moment BEFORE 7.2's capture;
- the preview's program is exactly `ip route 10.255.98.1 255.255.255.255 10.255.0.35`;
- the button reads `Re-apply 1 line(s) to tw-ztp-a`;
- confirm.

Verify waits for BGP's hold time. Expect it to pass, with BGP 0 → 1, and a receipt saying
`restore`.

**STOP 7. Paste:** the preview's program, the result, and the peer's `show bgp summary`.

## Part 8: retire, A3 (20 min)

v2, `tw-ztp-a`, Actions › **Retire…**:
1. The reason comes first, for example "throwaway session finished".
2. Read the plan's gates. Every one must pass, including "a break-glass export holds its
   current credential" (Part 4).
3. Type the confirmation, and confirm.
4. If offered, **Finish**: it removes Oxidized's row.

Expect the result to name what it did, and what it did not do: the NetBox device STAYS (Part 10
removes it), and the running configuration is unchanged.

**STOP 8. Paste:** the gates as drawn, the result, and its "not done" list.

## Part 9: the guestshell serial probe (20 min)

The question (section 16): can the IOS-XE ZTP mechanism read the device's serial, so that a
ZTP script could send it here? A ZTP Python script runs in guestshell and reaches IOS through
the same `cli` module used below. In this lab every C8000v reports one serial (C449), so this
measures the MECHANISM, not the value.

It runs after retire because it changes the device outside the tool. On the console:

    show license udi
    show version | include [Ss]erial|Processor board
    conf t
     iox
     end
    show iox-service

Repeat `show iox-service` until IOxman reads Running (a few minutes). Then:

    conf t
     app-hosting appid guestshell
     end
    guestshell enable
    guestshell run python3 -c "from cli import cli; print(cli('show license udi'))"
    guestshell run python3 -c "from cli import cli; print(cli('show version | include [Ss]erial|Processor board'))"

If `guestshell enable` refuses (for example, asking for an `app-vnic`), its message is the
result: paste it, and do not add networking for this. A refusal means guestshell needs network
configuration this ZTP state would not have. That is an answer.

**STOP 9. Paste:** each command's output (the serial itself is fine to paste here; it is the
lab image's shared serial), or the refusal.

## Part 10: cleanup and the census (30 min)

In this order:

1. **NetBox (today's page, NetBox tab).** The `throwaway` row › **Remove**:
   - every delete is named;
   - read what NetBox takes with them;
   - confirm;
   - read the result, then re-read it in the Removals panel.

   Expect the preview's count to be the executed count.
2. **The lab (lab host).**

       cd <home>/labs/throwaway && sudo containerlab destroy -t nmas-throwaway.clab.yml --cleanup
       ip -br link show master br-mgmt
       docker network ls --format '{{.Name}}' | grep -c throwaway-probe

   Expect `br-mgmt` back to `enp6s19`, `s3-mgmt` and `r6-mgmt`, and `0`. `--cleanup` was
   measured harmless to `br-mgmt` in P6's teardown.
3. **The census (NMAS host).**

       cd <home>/python/Agentic_NMAS && PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-netbox-census --compare /tmp/census-throwaway.json; echo "exit $?"

   Expect `exit 0`. Exit 1 means objects were left behind (it names them); exit 2 means it
   could not prove either.
4. **The Kea reservation (NMAS host).** A promoted ZTP device keeps its reservation, so it is
   removed by hand:

       cd <home>/python/Agentic_NMAS && PYTHONDONTWRITEBYTECODE=1 python3 -c 'from modules.nsot.ztp import write_reservations as w; print(w(removes=["aa:bb:cc:00:02:60"]))'
       sudo python3 <home>/python/Agentic_NMAS/docs/bootstrap-probe/kea-m5.py show

   Expect `removed` and `ok: True`, then 0 entries.
5. **The list (today's page).** Delete `throwaway`. Deleting a list never touches NetBox, which
   step 1 already cleared.
6. **The credential override (NMAS host).**

       cd <home>/python/Agentic_NMAS && PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-credential-overrides

   If `10.255.0.60` shows ORPHAN, clear it in Settings › Credentials (the tool will not delete
   it itself).
7. **The checkout is unchanged (NMAS host).** Expect nothing:

       cd <home>/python/Agentic_NMAS && git status --porcelain

8. **Job health.** `<home>/python/Agentic_NMAS/scripts/nmas-jobs`, and re-run any job that failed inside the session's window.
9. **The files on the lab host** (`/tmp/tw-*.pcap`, `/tmp/tw-discover-times.txt`) are yours to
   keep or delete. `<home>/labs/throwaway/` can stay for the next run.

**STOP 10. Paste:**
- the Remove result;
- the two lab-host checks;
- the census exit;
- the reservation removal and `show`;
- the override line;
- `git status` (empty).

## What each answer decides

- **Part 1 and 2:** what board L draws for a device not yet picked:
  - the expected next request;
  - a give-up warning, or "keeps asking until configured";
  - for a stopped device, its re-trigger.

  They also decide the discovery range's Kea host step, and the vendor-class design:
  - if option 60 arrives (`ciscopnp` was seen in M3), two pools and a client class;
  - otherwise MAC, client-id and hostname.
- **Part 5.2:** whether C178's hold watch is needed on IOS-XE in practice (it is built either
  way).
- **Part 5.3 to 8:** C117's real run (rollback), A2 and A3. Each closes or moves its register
  row.
- **Part 9:** whether way 1 (the device reports its serial) is possible on IOS-XE, or the list
  works from MAC and client-id only.
