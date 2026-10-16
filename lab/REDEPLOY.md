# Redeploying the lab (rcn-lab1), with its planned window and new SSH host keys

LAB TOOLING, not the product (the product's docs stay lab-agnostic: tests/test_lab_specifics.py).
Written 2026-10-16 for C906's follow-up: a redeploy builds every node from a fresh disk, so every
node comes back with a NEW SSH host key, and Mercury refuses a changed key unless a planned
window declared BEFORE the change says to expect one.

The verification after a redeploy is still `docs/STAGE2_SESSION_CHECKLIST.md` sections 1 and 4;
this page is the window and the keys around it. Real hosts, users and paths are in
`data/lab_hosts.json` (gitignored); here they are `<nmas-host>`, `<lab-host>`, `<user>` and
`<home>` (the user's home directory on each host).

## What is redeployed, and what Mercury knows of it

- The topology `<home>/labs/lab/rcn-lab1.clab.yml` on `<lab-host>` has nine network nodes, r1 to
  r5 and s1 to s4 (and hosts h1 to h4 and web). r6 is a separate lab (`clab-r6`) and is NOT
  redeployed by this.
- Network `Default` in Mercury holds r1 to r4, r6 and s1 to s4 (read 2026-10-16 from its Devices
  page). r5 is in the lab and not in Mercury, so Mercury never meets its key. The window below
  names the eight devices both hold, never `*`, which would also cover r6.

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
   expecting new SSH host keys: Mercury keeps one new key per device it meets inside the window, each in History; once the window closes, Needs attention says how many until a person acknowledges them
   ```

   Anything else is `refused: <why>` on stderr with exit 1: stop, and do not redeploy. A window
   that covers a restart Mercury has already seen is refused, so this step comes FIRST; and a
   window never accepts a key Mercury refused before the window was recorded.

2. **On `<lab-host>`, as `<user>`, at once:**

   ```bash
   cd <home>/labs/lab && sudo containerlab deploy -t rcn-lab1.clab.yml --reconfigure
   ```

   Never `docker restart` or `docker start` a node (C478).

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

5. **After the window closes** (`<until>` plus 15 minutes; the reader runs each minute): Needs
   attention shows ONE row, **"8 new host keys accepted during 'lab redeploy: rcn-lab1 rebuilt
   from its startup files'"**, naming each device's new key and the one it replaced. Review them
   in History, then **Acknowledge** with what you found. The row goes; the keys and the summary
   stay in History.

6. Then the post-items of `docs/STAGE2_SESSION_CHECKLIST.md` section 4, through Mercury.
