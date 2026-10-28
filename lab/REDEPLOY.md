# Redeploying the lab (rcn-lab1), with its planned window and new SSH host keys

LAB TOOLING, not the product (the product's docs stay lab-agnostic: tests/test_lab_specifics.py).
Written 2026-10-16 for C906's follow-up: a redeploy builds every node from a fresh disk, so every
node comes back with a NEW SSH host key, and Mercury refuses a changed key unless a planned
window declared BEFORE the change says to expect one.

The verification after a redeploy is still `docs/STAGE2_SESSION_CHECKLIST.md` sections 1 and 4;
this page is the window and the keys around it. Real hosts, users and paths are in
`data/lab_hosts.json` (gitignored); here they are `<nmas-host>`, `<lab-host>`, `<user>` and
`<home>` (the user's home directory on each host).

## How a lab node restarts: two ways only (the operator, 2026-10-19)

**A lab node is never restarted by containerlab (`restart`, `restart -n`) or by docker
(`restart`, `start`).** A node restarts in only two ways:

- a reload from its own CLI, which is Mercury's Reload, with its planned window;
- a full redeploy with the one redeploy command below, in its planned window.

Why: on 2026-10-19 the agent's `containerlab restart -n r5` moved r5's links into a park
namespace (`clab-park-<node>`) before it stopped the node, and they were never brought back. r3's
and r4's BGP sessions to r5 went down, and so did the path to the web server (C1372). Docker's own
restart and start were already refused for the configless launch (C478). A link added to the
topology reaches a node only through the redeploy.

## What is redeployed, and what Mercury knows of it

- The topology `<home>/labs/lab/rcn-lab1.clab.yml` on `<lab-host>` has nine network nodes, r1 to
  r5 and s1 to s4 (and hosts h1 to h4 and web). r6 is a separate lab (`clab-r6`) and is NOT
  redeployed by this.
- Network `Default` in Mercury holds r1 to r4, r6 and s1 to s4 (read 2026-10-16 from its Devices
  page). r5 is in the lab and not in Mercury, so Mercury never meets its key. The window below
  names the eight devices both hold, never `*`, which would also cover r6.
- **r5 is unmapped by design (the operator, 2026-10-19):** it is the handout's ISP router,
  outside the lab's administrative boundary, so it is declared `DECLARED-UNMAPPED` in the lab's
  map (`data/lab_targets/default.tsv` on `<nmas-host>`, gitignored, declared 2026-09-25) and
  boots from its startup file in the lab's own repository, never from Mercury's startup source.
  A redeploy that finds r5 unmapped is as intended.

## What each node boots, and the pre-flight (C1454)

Each node Mercury knows boots from its startup file, which the lab's startup sync
(`lab/clab-sync/clab-startup-sync.sh`) builds from Mercury's startup source,
`scripts/nmas-startup-source` (`modules/nsot/startup_source.py`):

- **The configuration is the device's newest golden recorded at its committed intent**: the
  newest commit whose `Intent-Match:` trailer judged the device and found it matching, so a
  verified per-device deploy is in the file the moment its capture is committed. An earned
  baseline counts for every device it holds, and the newest earned baseline is the fallback
  when no such commit is in the last 400 measurements. Until 2026-10-28 the source was the
  newest earned baseline alone, which a scoped deploy never earned, so a redeploy silently
  reverted every verified deploy since it (C1454).
- **A golden recorded off its intent, or unknown, is never a source** (C306): a change nobody
  approved never boots. Nothing older than the device's current golden file is a source, so a
  retired device's golden never boots the new device given its name.
- **Every credential family (accounts, enable, SNMP communities) is the current golden's**
  (C309), whatever commit the configuration comes from, so a rotation is never undone.
- **A device with no golden at its intent is NOT BUILT**, named with its reason; the others
  are still written. Bring it to its intent (its Deploy plan) and Save All, then build again.

**The pre-flight, before step 1, on `<nmas-host>` as `<user>`:**

```bash
<home>/python/Agentic_NMAS/scripts/nmas-startup-source --check --list Default
```

It writes nothing and prints one line per device: its **source commit and how it was recorded
at intent**, its latest golden commit and how many golden commits came after the source, and
every fact about the file. A device FAILS (exit 1) when a credential family differs from its
current golden, a masked placeholder is in the file, its golden is older than its last
rotation, the last drift run could not read it or **found it departing from its golden** (a
redeploy would undo that unrecorded change), the file lacks something Mercury needs to manage
it, or **its configuration is not its current golden's** (a golden committed after its source
and not recorded at its intent: the commits and the count of lines a redeploy would undo are
named, never a line). **Redeploy only on "N of N pass".** A failing device is resolved first:
bring it to its intent (Deploy plan) or adopt the change into intent, capture it, and check
again.

## The bound: 60 minutes, measured

The one full redeploy in Prometheus's record (sysUpTime, kept since about 2026-10-01), 2026-10-01:
the eight devices Mercury watches last answered at 16:43:20 to 16:44:05 UTC; the four switches'
counters restarted at 16:58:42 to 16:58:58 (+15.4 min) and the four C8000v routers' at
17:04:26 to 17:04:44 (+21.4 min); the last device answered again at 17:07:05, **23.8 minutes**
after the teardown. One C8000v alone boots in 6 min 30 s (reload_op's bound; r6 alone on
2026-10-09: 6.3 min to its counter, 8.8 min to its first answer): nine nodes booting together on
the lab host take three times as long. **The window is 60 minutes, about 2.5 times 23.8**, and a
restart or a new key up to 15 minutes after its end is still the window's
(`restarts.PLANNED_SLACK_SECONDS`), so Mercury accepts the new keys for 75 minutes.

Not inside the nightly backup window (08:30 to 09:10 UTC): start only when 08:30 UTC is more
than 75 minutes away, or after 09:10 UTC.

## The procedure

0. **Once, before the first redeploy that relies on this:** the release carrying C906 and this
   follow-up is deployed, and Mercury holds every device's key: Settings › Installation ›
   Diagnostics › Drift checks › **Check now** for Default, then History (`/v2/history?kind=hostkeys`)
   shows "SSH host key kept on first contact" for each of r1 to r4 and s1 to s4. A device whose key
   Mercury never held simply keeps its new key on first contact, with no window needed and
   nothing to compare it with.

1. **Before anything restarts. On `<nmas-host>`, as `<user>`** (the user the app runs as and who
   owns the checkout and its `data/`, 0700; never with sudo: the records are the app user's,
   0600):

   ```bash
   <home>/python/Agentic_NMAS/scripts/nmas-planned-restart Default r1 r2 r3 r4 s1 s2 s3 s4 \
       --minutes 60 --new-host-keys \
       --why "lab redeploy: rcn-lab1 rebuilt from its startup files" --by <operator>
   ```

   No wrapper in `~/bin` is needed (`~/bin` holds `nmas-deploy` and nothing for this). The
   script re-runs itself under the app's interpreter (the virtualenv `flask-app.service` runs,
   read from systemd) and says so on stderr. **It passed when it exits 0 and prints**, on
   stdout:

   ```
   recorded: r1, r2, r3, r4, s1, s2, s3, s4 in Default may restart from <from> until <until> (and up to 15 min after), by <operator>: lab redeploy: rcn-lab1 rebuilt from its startup files
   window recorded <recorded_at> (id <id>); if the attempt is abandoned, end it at once: nmas-planned-restart Default --end <recorded_at> --why "<why>"
   expecting new SSH host keys: Mercury keeps one new key per device it meets inside the window, each in History; once the window closes, Needs attention says how many until a person acknowledges them
   ```

   Keep `<recorded_at>`: it names this window if the attempt is abandoned (below).

   Anything else is `refused: <why>` on stderr with exit 1: stop, and do not redeploy. A window
   that covers a restart Mercury has already seen is refused, so this step comes FIRST; and a
   window never accepts a key Mercury refused before the window was recorded.

2. **On `<lab-host>`, as `<user>`, at once:**

   ```bash
   cd <home>/labs/lab && containerlab deploy -t rcn-lab1.clab.yml --reconfigure
   ```

   Never `docker restart` or `docker start` a node (C478). **The one redeploy command**, the same
   in `docs/STAGE2_SESSION_CHECKLIST.md` 3.2 (chosen 2026-10-16, confirmed by the operator
   the same day, STANDING_APPROVAL_LOG): `--reconfigure` regenerates the lab's artifacts, so
   every node boots from its startup file, as the checklist's former `destroy --cleanup` then
   `deploy` did, in one command (containerlab 0.79.0's help: "Regenerate configuration
   artifacts and overwrite previous ones if any"); C478's fix already uses it. No `sudo`:
   `<user>` is in `clab_admins` on `<lab-host>` (read 2026-10-16), which containerlab lets run
   it; the lab folder is root-owned from earlier `sudo` runs, so if this refuses on permissions,
   the same command with `sudo` is the fallback, and say so in the report.

3. **Within the window (by `<until>` plus 15 minutes), once all eight answer** (the Devices page;
   expect about 24 minutes): Settings › Installation › Diagnostics › Drift checks › **Check now**
   for Default. Its session to each device meets the device's new key and keeps it under the
   window. (The restarts reader's one read of each restarted device's reload reason may meet
   some keys first; Check now makes sure every device is met inside the window.)

4. **Check, while the window is open:**
   - History (`/v2/history?kind=hostkeys`): one row per device, "SSH host key kept under a planned
     window", reading `SHA256:<new> (ssh-rsa), replacing SHA256:<old>, during 'lab redeploy:
     rcn-lab1 rebuilt from its startup files'`;
   - Needs attention: no "restarted unexpectedly" row for these eight, and no "answered with a
     different SSH host key" row. Such a row means a device was met with a new key outside the
     window: review it with Re-key… on its page.

5. **Once every device has answered with its new key** (step 3's Check now; the reader runs
   each minute), the window ENDS then, not at `<until>` plus 15 minutes (C1389): it covers
   nothing more, so it takes no stray key and covers no later restart, apart from the 15-minute
   slack a restart's estimated time gets after the end. History shows the early end on the
   window's row. Within a minute Needs attention shows ONE row, **"8 new host keys accepted
   during 'lab redeploy: rcn-lab1 rebuilt from its startup files'"**, naming the window by its
   times and each device's new key with the one it replaced. Review them in History, then
   **Acknowledge** with what you found. The row goes; the keys and the summary stay in History.
   If a device never answers with a new key, the window runs to `<until>` plus 15 minutes and
   the row appears then.

## When an attempt is abandoned: end its window at once (the operator, 2026-10-19, C1389)

If the redeploy stops before it runs (a node that cannot be removed, a host that needs a reboot
first), **end its window at once, on `<nmas-host>` as `<user>`**:

```bash
<home>/python/Agentic_NMAS/scripts/nmas-planned-restart Default --end <recorded_at> \
    --why "<what stopped the attempt>" --by <operator>
```

It prints `ended: the window recorded <recorded_at> … window ended <now> (…)` and exits 0. An
ended window takes no new key and covers no later restart. Then declare a FRESH window (step 1)
for the attempt that will run, immediately before it runs.

Why: on 2026-10-19 the first attempt's window (W1, recorded 19:16:50Z) was left open when the
attempt failed at r5, and the redeploy that ran after the lab host's reboot declared a second
one (W2, 19:25:29Z) for the same eight devices and r6. Mercury credited the eight new keys to
the FIRST covering window, W1, the abandoned one. Mercury now credits a key to the LATER of two
overlapping windows (a later declaration for a device supersedes an earlier one from its
recording on), and a window whose devices have all been taken over by a later one ends when
that one opens. Ending the abandoned window at once still matters: it then covers no restart
either. A key already credited to the wrong window is corrected with
`scripts/nmas-host-key-recredit` (it prints its plan; `--apply --every --by <operator>` makes
the correction, kept in History), never by editing the record.

An end recorded after the fact (`--at <when it was abandoned>`) changes what was already
judged, so it needs `--correction "<why it is recorded late>"`.

## After the redeploy

6. Then the post-items of `docs/STAGE2_SESSION_CHECKLIST.md` section 4, through Mercury (its
   revision of 2026-10-16, C948). They are the same steps, not a second set: its 3.2 is steps 1
   and 2 here, its 4.1 read is each device's first session inside the window, its 4.8 is step
   3's Check now, and its 4.12 is steps 4 and 5.
