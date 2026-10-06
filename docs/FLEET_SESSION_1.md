# Fleet session 1: the short fleet session (NSOT_STAGE7_PLAN section 12)

One sitting on the FLEET, in this order, every command complete. **s3 is last wherever it is
involved, and nothing here runs inside the nightly backup window, 08:30 to 09:00 UTC (02:30 to
03:00 your time).** No part reloads a device. The probes change running config only and never
save; the deploys push and save; neither restarts anything.

| Part | What | Who and where | Time |
|---|---|---|---|
| 0 | before you start: the version, the window | you | 5 min |
| 1 | staged run 6: does vIOS answer `freeMem` (on s1) | you, the NMAS host, read-only | 5 min |
| 2 | C230: the Grafana Viewer token | you, Grafana and Settings; one check on the host | 20 min |
| 3 | C100: the NetBox service account | you, NetBox and Settings; checks on the host | 35 min |
| 4 | staged run 1: the silenced-alert capture (on s1) | you, the console, Grafana; capture on the host | 30 min |
| 5 | staged run 4: `global.ntp-server` and `global.snmp-server-host` (r2, s4) | you, the NMAS host | 20 min |
| 6 | staged run 9, part 1: the IP SLA delete measured on s1 and r2 | you, the NMAS host | 20 min |
| PAUSE | I commit Part 6's verdicts; CI; you deploy (`nmas-deploy --wait`) | me, then you | about 25 min |
| 7 | C269: `cdp run` out of r1 to r4's intent, then one batch | you, through the tool | 45 min |
| 8 | staged run 9, part 2: s3's IP SLA from 10 s to 60 s | you, through the tool | 20 min |

**About 3 hours 45 minutes,** including the 25-minute pause in the middle. There are two
natural breaks: after Part 3 (only accounts have changed) and the pause after Part 6 (the
probes are done; the tool is being updated). C262 (r6's `cdp run`) is not here: it was done on
2026-10-01 (r6's deploy batch-b43145) and is closed. The browser break-glass export is not here
either: the record's first real run passed on 2026-10-03, and the throwaway session exports again.

**Times:** write every time as UTC (`date -u +%FT%TZ`).

**Commands on the NMAS host** run in the live checkout's folder, always with
`PYTHONDONTWRITEBYTECODE=1` (no `__pycache__` in the checkout):

    cd <home>/python/Agentic_NMAS

## Part 0: before you start (5 min)

1. The host runs a commit CI passed (`nmas-deploy --wait` if not), and the throwaway session is
   finished (its lab destroyed, its list deleted).
2. It is not between 08:30 and 09:00 UTC, and the session ends before 08:30.
3. Needs attention has no row naming r1 to r4, r6, s1 to s4 that you have not already read.

**STOP 0.** Nothing to paste.

## Part 1: staged run 6, does vIOS answer `freeMem` (5 min, read-only)

On s1, never s3 (s1's management address 10.255.1.21, read from its golden on 2026-10-05). The
community comes from the SNMP exporter's file and is never printed:

    C=$(sudo python3 -c 'import yaml; print(yaml.safe_load(open("/etc/snmp_exporter/snmp.yml"))["auths"]["public_v2"]["community"])')
    snmpget -v2c -c "$C" -On -t 5 10.255.1.21 1.3.6.1.4.1.9.2.1.8.0; unset C

Expect one of:
- `.1.3.6.1.4.1.9.2.1.8.0 = INTEGER: <n>`: vIOS answers. The memory panel's fold for vIOS
  (`panels.PLATFORM_FOLDS`) goes, and the vIOS module reads freeMem;
- `No Such Object available on this agent at this OID`: an answer, not a failure. The panel
  keeps folding, now measured.

**STOP 1. Paste:** the one line `snmpget` printed.

## Part 2: C230, the Grafana Viewer token (20 min)

**What the tool needs: Viewer, nothing more** (read from the code, 2026-10-05). Every
Grafana call is a GET, except `POST api/ds/query`, which is a datasource query (a read):

| Call | For | Viewer |
|---|---|---|
| `GET api/user` | Settings' Test, the integrations reader (every 60 s) | yes (any signed-in identity) |
| `GET api/health` | the probe with no token; the accounts script | yes (no auth) |
| `GET api/access-control/user/permissions` | `nmas-integration-accounts` | yes (its own list) |
| `GET api/search?type=dash-db`, `GET api/dashboards/uid/<uid>` | the dashboards reader; Monitoring; a device's Monitoring tab | yes, in folders that give Viewer View (the default) |
| `GET api/frontend/settings` | the datasource list | yes |
| `GET api/datasources` | each datasource's address, for host step 14.14 only (no page draws it; a refusal is soft) | uncertain: the `all:` line below says |
| `POST api/ds/query` | every panel; folds and guards; History's long ranges | yes, while each datasource gives Viewer **Query** (the default) |
| `GET api/datasources/proxy/uid/<uid>/api/v1/label/<label>/values` | a device's dashboard variable | yes (Query) |
| `GET api/ruler/grafana/api/v1/rules`, `GET api/prometheus/grafana/api/v1/rules` | the alerts reader (every 60 s) | yes (`alert.rules:read`), but only rules whose datasources Viewer can Query |
| `GET api/alertmanager/grafana/api/v2/alerts`, `…/silences` | the alerts reader; who silenced what | yes (`alert.instances:read`, `alert.silences:read`) |

**Writes: none.** The tool never creates or expires a silence (it only reads them), and
acknowledgements stay in the tool. It writes no annotation, imports no dashboard
(`nmas-device.json` is imported by hand), and installs alert rules only as root host steps
(provisioned files), never through the token. So nothing is moved out of the app: it is
already out.

**Two ways a Viewer read silently returns less** (200, fewer items): a datasource whose Query
permission excludes Viewer, or a folder that does not give Viewer View. Steps 2.4 and 2.5
make both visible.

1. **Grafana › Administration › Users and access › Service accounts › Add service
   account:** display name `nmas-reader`, role **Viewer**. Then **Add service account token**:
   set an expiry (a date you will renew by) or none. The token is shown ONCE.
2. **The tool, today's Settings › Integrations › Grafana:** paste the token; fill **Token
   expires** (YYYY-MM-DD, or `never`: P.21 warns 30 and 7 days ahead); **Save**; **Test**.
   Expect "Connected; the token is accepted".
3. **On the NMAS host:**

       PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-integration-accounts; echo "exit $?"

   Expect `Grafana <version>: the stored token holds N permission(s)`, then `  no create,
   write or delete: a reader's token`, then the `  all: …` line, and `exit 0` (it may print the
   NetBox line first; it exits 1 only for a Grafana write). Note whether `all:` holds
   `datasources:read`.
4. **Within a minute, `/v2/attention`:**
   - no Integrations row for Grafana;
   - under What was checked, "Grafana alerts" fresh, with rules counted;
   - **no "device(s) have no heartbeat rule Grafana shows" row** (that row would mean Viewer
     cannot Query Loki);
   - job health's `reader:grafana-alerts` and `reader:grafana-dashboards` rows ok.
5. **`/v2/monitoring`:** the dashboard selector lists the dashboards and the fleet panels draw,
   none saying "Grafana: HTTP 403". Then a device, `/v2/device/s1/monitoring`: the variable
   state reads listed, and the panels draw.
6. **Delete the old Editor token:** Grafana › Administration › Service accounts › the old
   account › its token › Delete. Then repeat step 3's command: still `exit 0`.

**STOP 2. Paste:** the Test result, step 3's output (the `all:` line included), and anything
steps 4 and 5 showed that was not as expected. C230 closes on `exit 0`.

## Part 3: C100, the NetBox service account (35 min)

**What the tool needs** (read from the code, 2026-10-05; `docs/SERVICE_ACCOUNTS.md` part 1
with three corrections):
- **Always, even with NetBox writes off: view** on every type below. Onboarding, import,
  Remove's previews, the device page's NetBox tab, the context and secret readers, and the
  host scripts all read.
- **Only with `netbox_allow_writes` on: add, change, delete**, for onboarding phase 2, adopt,
  Abandon, import and Remove's apply, retire's context mask, and the host scripts' `--apply`.
- Every "admin" type (manufacturer, device type, role, platform, tag, custom field, config
  template) is get-or-create: an existing one is reused, and one is created only when absent.

The three corrections to SERVICE_ACCOUNTS 1.3 and 1.4:
1. **View also needs Users › token.** The credential-health reader reads the token's own row
   (`GET /api/users/tokens/`) to know its expiry. Without it, P.21 cannot track the NetBox
   token. The document's "nothing under Users" was wrong for this one type, view only.
2. **No constraint on delete, for now (C466).** The tool reads a 404 on DELETE as "already
   gone". NetBox answers a delete refused by a constrained permission with 404, so a
   constraint that ever refused would read as a success, and the tool would forget it created
   the object. The tool already deletes only what is tagged AND recorded. Add the constraint
   after C466 is fixed. **Never constrain view** (a hidden object reads as gone).
3. **Allowed IPs: leave empty, for now.** NetBox runs in docker on the NMAS host, so the
   source address it sees is not measured, and the tool's Test hides NetBox's refusal reason
   (C468). A wrong address would read only as "Authentication failed".

**1. Before anything changes (NMAS host, with the CURRENT token still stored):**

    PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-integration-accounts
    PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-netbox-census --out /tmp/census-before-switch.json && test -s /tmp/census-before-switch.json && echo "baseline present"

Also, in today's NetBox tab, open the Default row's **Sync** preview and write down its create
and update counts. You compare them after the switch.

**2. The user:** NetBox › Admin › Authentication › Users › Add: username `nmas`, a long random
password recorded nowhere, Active yes, Staff no, Superuser no.

**3. Four permissions** (Admin › Authentication › Permissions › Add), each assigned to `nmas`:

| Name | Actions | Object types |
|---|---|---|
| `nmas-view` | view | DCIM › cable, device, device role, device type, interface, manufacturer, platform, region, site; IPAM › IP address, prefix, role, VLAN, VRF; Extras › config template, custom field, tag; VPN › tunnel, tunnel termination; Core › object change; **Users › token** |
| `nmas-add` | add | DCIM › cable, device, device role, device type, interface, manufacturer, platform, region, site; IPAM › IP address, prefix, role, VLAN, VRF; Extras › config template, custom field, tag; VPN › tunnel, tunnel termination |
| `nmas-change` | change | DCIM › device, interface, site; IPAM › IP address, prefix; Extras › config template |
| `nmas-delete` | delete | VPN › tunnel; IPAM › IP address, prefix, VLAN, VRF; DCIM › interface, device, site, region. **No constraint** (C466) |

Nothing under Authentication, and no delete of a tag.

**4. The token:** Admin › Authentication › API Tokens › Add:
- user `nmas`;
- version 2 (the `nbt_…` form; the expiry reader identifies its own row by the v2 key);
- **Write enabled: yes**;
- **Expires:** a date you will renew by. The tool reads it from NetBox itself (with step 3's
  Users › token view), so P.21 tracks it; NetBox has no "Token expires" field in Settings;
- Allowed IPs: empty (above);
- description `NMAS (C100)`.

It is shown ONCE.

**5. The tool:** today's page › Settings (the modal) › **NetBox** section: paste the token
(`nbt_…`, sent as `Authorization: Bearer`), **Save Settings**, then **Test Connection**. Write
down the UTC time.

**6. Prove the reads (NMAS host, then the tool):**

    PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-integration-accounts
    PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-netbox-census --compare /tmp/census-before-switch.json; echo "exit $?"
    PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-netbox-untagged; echo "exit $?"

Expect:
- `the stored token acts as 'nmas'`;
- census `exit 0`. Since C467 (2026-10-05) it walks every type the tool reads: 19 compared,
  plus the change log and tokens read and never compared. A refused read exits 2 (UNPROVEN),
  naming the type. A baseline taken by the older script holds 13 types, and compares as
  "present in only one census", so take the baseline with the version this session runs;
- `nmas-netbox-untagged` exits as it did before the switch, and never 2 (UNPROVEN). It reads
  every recorded object by id across every type the tool created, and the change log.

In the tool:
- today's NetBox tab, the Default row's **Sync** preview: the same create and update counts as
  step 1. A create of something that exists means a missing view;
- `/v2/device/r1` › NetBox tab: the device, with its interface and address counts;
- `/v2/attention` › What was checked: the NetBox secrets source fresh, and the credential
  health entry for the NetBox token showing its expiry (that proves Users › token).

**7. Prove the writes:** nothing on the fleet's NetBox should be written just to test. The
writes are proven by the next onboarding with this token:
- phase 2 creates across the add types and changes the device;
- its teardown's NetBox Remove deletes;
- its report names any refused write as "POST <type> failed (403)", and Remove's result names
  any refused delete.

The throwaway session does exactly this. **If you switch before the throwaway's Part 3, it
proves all three verbs.** If you switch after it, the proof waits for the next onboarding,
and until then the first write's report is the check. Do not use Remove on a real list as a
test.

**8. Retire the old token:** NetBox › Admin › Authentication › API Tokens: delete your own
(superuser) token that the tool used, unless something else uses it. Then run step 6's first
command again: still `acts as 'nmas'`.

**STOP 3. Paste:** step 6's three outputs, the Sync preview's counts before and after, and
the credential-health line. C100 closes on step 6.

## Part 4: staged run 1, the silenced-alert capture (30 min)

The first real silence object, to replace the provisional fixture. On s1, never s3.

1. **Send a critical log line on s1** (its console, on the lab host):

       docker exec -it clab-rcn-lab1-s1 telnet localhost 5000

   Log in with the break-glass record's credential (s1's console asks once C455 reaches it;
   until then it does not). At `s1#`:

       send log 2 NMAS silence capture

   Then leave the console with `Ctrl-]` and `quit`.
2. Within about 2 minutes (the rule's 60 s evaluation), Grafana shows "Critical syslog
   received" firing for s1, and Needs attention has its row.
3. **Silence it in Grafana:** Alerting › Silences › New silence:
   - matchers `alertname = Critical syslog received` and `device = s1`;
   - duration 15 minutes;
   - comment `NMAS silence capture`.
4. Within 60 s, the Needs attention row ends "(silenced in Grafana)", keeps its level, and says
   "silenced in Grafana by <you> until <the end>".
5. **The capture (NMAS host, read-only, into /tmp, never the checkout):**

       PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-capture-grafana-alerts --out /tmp/grafana-silenced

   Expect `captured ruler, rules_view, alertmanager, silences at <UTC> into /tmp/grafana-silenced`.
6. **Expire the silence** in Grafana (Silences › the row › Expire), then:

       PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-capture-grafana-alerts --out /tmp/grafana-expired

**STOP 4. Paste:** the two `captured …` lines, the Needs attention row's words while
silenced, and the time you silenced it. I fetch the two folders read-only and replace the
provisional fixture. Your identity in the silence's author field becomes `<operator>` before
anything is committed.

## Part 5: staged run 4, two removal shapes measured (20 min)

Running config only, never saved, the device held for the run. On r2 (IOS-XE) and s4 (IOS),
never s3.

1. The dry run (connects to nothing):

       PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-removal-probe --shape global.ntp-server --shape global.snmp-server-host

   Expect each shape's `add`, `remove` and `teardown` lines, with documentation addresses
   (192.0.2.11, 192.0.2.12) and the scratch community `NMASPROBE4`.
2. r2:

       PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-removal-probe --list Default --device r2 --shape global.ntp-server --shape global.snmp-server-host --apply --actor <operator> --out /tmp/removal-r2.json; echo "exit $?"

3. s4: the same with `--device s4 --out /tmp/removal-s4.json`.

Expect one line per shape (`<shape>: exact` or another verdict, with its detail), `written:
<path>` and `exit 0`, whatever the verdicts. **`exit 2` is NOT RESTORED: stop, and paste the
first line.** The probe's message names what differs; a reload would return the device. If you
reload, first declare the window:

    PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-planned-restart Default <device> --minutes 20 --why "the removal probe did not restore <device>" --by <operator>

**STOP 5. Paste:** both runs' output lines. I fetch the two files read-only.

## Part 6: staged run 9, part 1: the IP SLA delete measured (20 min)

IOS refuses to modify a running IP SLA operation ("Entry already running and cannot be
modified"), so the tool deletes and re-creates it. That delete is allowed only once measured
`exact` on the platform. Measured here on s1 (IOS) and r2 (IOS-XE), never s3.

1. The dry run:

       PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-removal-probe --shape global.ip-sla-operation

   Expect two scratch operations, both removed by `no ip sla <n>`:
   - 9901, scheduled: `ip sla 9901` / ` icmp-echo 192.0.2.13` / ` frequency 60` / `ip sla schedule 9901 life forever start-time now`;
   - 9902, unscheduled: `ip sla 9902` / ` icmp-echo 192.0.2.14` / ` frequency 60`.
2. s1, then r2:

       PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-removal-probe --list Default --device s1 --shape global.ip-sla-operation --apply --actor <operator> --out /tmp/removal-ipsla-s1.json; echo "exit $?"
       PYTHONDONTWRITEBYTECODE=1 python3 scripts/nmas-removal-probe --list Default --device r2 --shape global.ip-sla-operation --apply --actor <operator> --out /tmp/removal-ipsla-r2.json; echo "exit $?"

Expect `global.ip-sla-operation: exact` (the operation and its own schedule line gone, nothing
else) and `exit 0`. `broader` keeps the re-create refused, naming what went. `exit 2`: as in
Part 5.

**STOP 6. Paste:** both runs' output lines.

## PAUSE: the verdicts reach the tool (about 25 min)

Part 8 needs Parts 5 and 6's verdicts in `modules/nsot/removal_measured.json`, on the host:
1. I fetch the four files read-only, add the verdicts with their device and time, and push.
2. CI runs (about 10 min).
3. You deploy: `nmas-deploy --wait`.

While CI runs you can do Part 7's first half (the intent edits), which needs nothing new.
Without the deploy, s3's plan in Part 8 refuses: "`global.ip-sla-operation` has not been
measured on cisco_ios".

## Part 7: C269, `cdp run` out of r1 to r4 (45 min)

Measured 2026-10-05: r1 to r4 each carry `cdp run` in their intent and their golden; on IOS-XE
it enables nothing (no interface runs CDP), and `global.cdp-run` is measured `exact` on IOS-XE
(staged run 8, r2), so Mode B may remove it.

1. **The intent, one commit per device:** for each of r1, r2, r3 and r4, open the editor
   (`/?open=intent_editor&device=r1&list=Default`, today's page), delete the `cdp run: true`
   line under `flags` (delete it: setting it to `false` would render `no cdp run` as intent),
   **Check & show diff** (one line removed), a summary such as `C269: cdp run enables nothing on
   IOS-XE`, **Commit**.
2. **One batch:** v2 Devices, tick r1, r2, r3 and r4, **Plan a deploy for the ticked devices
   (today's page)…**. Each device's plan offers `cdp run` for removal: tick it on each, with the
   reason `C269: CDP enables nothing on IOS-XE here` (the reason is in the hash and the receipt).
   Read each program: `no cdp run` and nothing else. **Deploy confirmed devices.**

Expect each device: pushed, verified (FULL, so BGP devices wait out their hold time: r3 and r4
take 3 to 4 minutes each), golden committed with `Intent-Match: yes`. The batch stops at its
first failed verify, which rolls that device back.

**STOP 7. Paste:** the batch's result headline and each device's line.

## Part 8: staged run 9, part 2: s3's IP SLA, 10 s to 60 s (20 min, LAST)

Only after the PAUSE's deploy. s3's probe to r1 (`ip sla 1`, `icmp-echo 10.255.1.11
source-interface Loopback0`, `frequency 10`, read from its intent and golden on 2026-10-05).
Still waiting (the operator, 2026-10-06). It also eases s3's CPU: s3 is starved (C93), and this
probe's ping every 10 s runs through it today, as the fleet's continuous pings do.

1. **The intent:** open the editor for s3 (`/?open=intent_editor&device=s3&list=Default`),
   change ` frequency 10` to ` frequency 60` under `ip_sla` › id `'1'` › `settings`, **Check &
   show diff** (one line), summary `C290: s3's IP SLA probe to 60 s (C93)`, **Commit**.
2. **The deploy:** s3's v2 page, **Actions › Plan a deploy…**. The program is exactly six lines,
   under the note "ip sla 1 is running … What it replaces on the device":

       no ip sla 1
       ip sla 1
        icmp-echo 10.255.1.11 source-interface Loopback0
        frequency 60
       exit
       ip sla schedule 1 life forever start-time now

   **If anything else is in the program, cancel and paste it.** Otherwise confirm.
3. Expect: pushed, verify reads `ip sla 1` back (a read-back that differs fails verify, and the
   rollback restores `frequency 10`), golden committed with `frequency 60`. The probe's counters
   and history start again.

**STOP 8. Paste:** the result headline, and the time. C290 closes when s3's golden reads
`frequency 60`; C93's measurement (s3's CPU) follows over the next day.

## What each part closes

- Part 1: the vIOS memory panel's fold, kept or removed (no register row).
- Part 2: C230. Part 3: C100.
- Part 4: the provisional silence fixture (no register row).
- Part 5: two Mode B shapes measured (no register row).
- Parts 6 and 8: C290; P.9's last staged run.
- Part 7: C269.
