# Rotate a credential

Rotation replaces the password the tool uses to sign in to one device with a new one the tool generates, records it, and then makes the device keep it across a reload. It is the riskiest operation in the tool, so the order of the steps is the lockout defence: the old session stays open until the new password is proven, only a failed proof undoes the change, and every state between "the device changed" and "the tool holds the new password" is named and recoverable.

![Rotation: the preview reads the account's line from the device and sends nothing; the apply stages a generated password on the tool's host, sends the new account line on a held session, proves it on a fresh login (a failed proof puts the old line back on the held session), records it in the credential store, the inventory and one commit, then persists: the device's own save, read back.](diagrams/rotate.svg)

You start it from the device's page: Actions > Rotate credential on the redesigned page, whose card reads the account's line, shows the plan and, after the confirm, waits for the job and draws its result in place (a card refused because another operation holds the device reads again when the tool announces that operation finished); or Rotate credential… on today's page. Both reach the same plan and confirm (`/v2/device/<name>/rotate/*`, `/rotate/*`). The same implementation also runs on the host as `nmas-rotate-credential`.

## The preview

1. **Preflight** (`preflight`). Read: the device's inventory row; its manifest identity; its committed golden; and the account's `username` line read live from the device (`show running-config | include ^username <account>`). Sent: nothing that changes the device (one read on a session that is closed again). Recorded: nothing. The program depends on whether the account holds a `secret` or a `password` on the device now, not in a stored capture, and each check is drawn by name as a gate; any one failing refuses the rotation before anything changes.
2. **The program is shown**. Read: nothing more. Sent: nothing. Recorded: nothing. It is the exact program for this device, the new password masked: one line (`username <account> privilege <n> algorithm-type scrypt secret <generated>`) when the account holds a secret, or `no username <account>` first and then that line when it holds a password, because the device refuses a secret over a password entry. Beside it are who else signs in as this account and what happens to each.
3. **The fingerprint**. Read: nothing more. Sent: nothing. Recorded: nothing. You confirm the plan's fingerprint, which binds the account's line and its entry kind; the apply computes it again and refuses a different one with nothing sent.

## The apply

The apply runs as a job, holding the device from start to finish, so no other operation can touch it meanwhile. The window can close; the in-flight panel shows it, and its result is read by its job id when it finishes. It runs as you: the job carries your verified identity into its thread.

1. **Preflight and confirmation, again** (`preflight`, `confirmation`). Read: everything the preview read, including the live account line. Sent: nothing. Recorded: nothing. A plan that moved since you confirmed refuses with nothing sent.
2. **Generate** (`generate`). Read: nothing. Sent: nothing. Recorded: nothing. A 32-character password is generated from a fixed character set of letters, digits and punctuation, and checked by the same guards the deploy path uses before it is accepted.
3. **Stage** (`stage`). Read: nothing. Sent: nothing. Recorded: the new password, encrypted, in a staging file inside the list's repository folder on the tool's host (never committed). It exists before anything is sent, so a crash after the device accepts it cannot lose the only copy.
4. **Make redaction know the new value** (`invalidate_redaction_cache`). Read: nothing. Sent: nothing. Recorded: nothing. Every log line after this masks the new password.
5. **Open and hold the original session** (`original_session`). Read: `show clock`, to prove the session works. Sent: nothing that changes the device. Recorded: nothing. This session, signed in with the old password, stays open until the new password is proven: it is the one way back. If it cannot be opened the staged copy is removed and the rotation is refused before the push.
6. **Re-check the entry kind** (`recheck_entry_kind`). Read: the account's line again, on the held session. Sent: nothing. Recorded: nothing. A device whose account changed from password to secret (or back) since you confirmed is refused, because the program you confirmed would no longer be the one sent.
7. **Push** (`push`). Read: the device's answer. Sent: the program from the preview, with the real password, on the held session. Recorded: nothing. A rejected command stops the rotation with the device unchanged.
8. **Verify on a fresh login** (`verify_new_credential`). Read: a new SSH login with the new password, then `show running-config | include ^username`. Sent: nothing. Recorded: nothing. The held session would succeed whatever the device now believes, so only a fresh login proves the change. A local fault (no connection made) is retried; a refusal by the device is the one result that undoes the change: the old line is sent back on the held session and then proven with a fresh login on the old password.
9. **Check the stored form** (`captured_type_9`). Read: the account's line from the verify's read. Sent: nothing, unless the device did not store a type 9 hash, in which case the old line is sent back as in step 8. Recorded: nothing.
10. **Capture** (`post_capture`). Read: the whole running configuration, on the held session. Sent: nothing. Recorded: nothing yet. Then the held session is closed.
11. **Record** (`commit`). Read: the device's committed intent. Sent: nothing. Recorded: the device's hash as the account's template secret in the credential store; the new password in this device's inventory row only (encrypted, the separate enable column emptied); the intent changed to reference the secret; the old plaintext template secret deleted; and one commit of the golden and the intent, as you, with `Source: rotation`. If the capture in step 10 was not a whole configuration, the golden is left as it was and the credential and intent are still recorded.
12. **Clear the staged copy**. Read: nothing. Sent: nothing. Recorded: the staging file is removed, only after the commit succeeded. If the record failed, the staged copy is kept, because it is then the only copy.
13. **Persist** (see [Persist](persist#the-host-chain)). Read and Sent: as that page says. Recorded: a persist row. The device's own save and read-back: a reload boots that, so it is what is proved. The commit in step 11 also writes the golden-committed event, which a tool building a boot file elsewhere follows.

### While it runs

The card shows the rotation in six steps, each done with its time, running (since when, and
what it waits on), or waiting. Each step groups the numbered steps above:

- **Read the account** (`read_account`): step 1, the preflight and confirmation read again.
- **Stage the new password** (`stage`): steps 2 to 4.
- **Send** (`send`): steps 5 to 7.
- **Fresh login** (`fresh_login`): steps 8 and 9, and putting the old line back if the login
  is refused.
- **Record** (`record`): steps 10 and 11.
- **Persist** (`persist`): step 13, naming each stage of the chain as it finishes.

## The outcomes

The result names one state, with its one next step:

- **rotated and persisted**: export the break-glass record again;
- **rotated, persistence not attempted**: the most dangerous state. The device runs the new credential and its startup config still holds the old one, so a reload would boot the old credential. The result's one button is **Persist**, which opens the device's Persist card in place (it saves the running config to startup and reads it back); then export the break-glass record. Needs attention shows the same row, with the same Persist button, until a persist reads SAFE;
- **rotated, persistence unverified**: the device's save or its read-back did not prove the new credential (the result names the stage). Do not reload the device. The remedy is the device's own save again: **Persist**, on the result and on Needs attention (or `nmas-persist-native` on the host);
- **rotated, not recorded**: the device holds a password the tool did not record. The staged copy is kept and is the only copy; run `nmas-rotation-recover` for it;
- **reverted**: the device is unchanged, and the result says why the verify failed;
- **revert failed**: the device refused the old password after the revert; recover it on its console with the break-glass record;
- **reverted, proof inconclusive**: the old line was sent back and the proof could not run locally; check the device directly;
- **failed before any change**: nothing was sent; read the refusal, fix it, and preview again.

Every rotation and every persist writes a row (each step's name, outcome and reason, never a credential) where job health reads it, and the device's rotation row stays on Needs attention until a persist reads SAFE.

## What rotation does not do

- It does not change the template, so no approval is revoked.
- It changes no other device and no shared credential profile.
- It does not change the enable secret: the account's login line only.
- It does not remove the old password from git history: after the rotation that is a dead credential.

## After a rotation

The break-glass record holds the old password, so the result's next step is a new break-glass export. Until it is exported again, Needs attention has one row for the network's record, naming every device rotated since its export (a rotation from the device page and a scheduled one alike).

## On a schedule {#scheduled}

A credential profile on Credentials › Profiles can carry a **rotation policy**: off, or every N days (30 unless you say otherwise; 1 is allowed), a preferred window in UTC hours, and at most K devices a run. Only a verified person sets one, with Rotation policy… on the profile's row, and History records who, when and what. A device follows the policy of the profile the resolver would give it a login from, the most specific that exists (`role:<role>`, then `site:<site>`, then `default`), and that profile's policy alone, off included.

A device's **credential age** is read from the rotation record: its last rotation that reached the device. A device with none is "never rotated by Mercury" and counts as due. Credentials › Profiles shows each device's age and next due date, grouped (due now, within their policy, no policy on), and the device page's Overview shows its own as the Credential check.

A timer in the app looks every five minutes. A policy's run happens inside its preferred window, at most once a UTC day; **Rotate due devices now** on Credentials › Profiles runs the same thing at once, as you, outside the preferred window too, after a preview of the devices it takes and confirmed by that preview's hash. A run, in order:

1. **Refuse** (`refuse`). No run starts inside the nightly backup window, 08:30 to 09:10 UTC, or while another run is going (one at a time, across processes; the second is refused naming the first). The timer also starts no run while the last run's failure stands.
2. **Select** (`select`). The due devices, oldest credential first (never rotated first), at most each policy's limit; the rest wait for the next run, each with why.
3. **Check** (`check`). Before each device: skipped, with the reason recorded, when another operation holds it, when it is mid-restart (a planned-restart window covers now, or it restarted in the last ten minutes), when its committed golden is off its intent, or when its plan cannot be made (unreachable, or its account line unreadable).
4. **Rotate** (`rotate`). The device-page rotation itself, one device at a time: the same plan, the same steps above (read the account, stage, send, fresh login, record, persist), the same record and commit. History draws it as "Scheduled rotation (policy set by <person>)"; the commit's `Actor:` is the policy's setter (you, for Rotate due devices now) and its `Source:` is `scheduled-rotation`. A timer's commit reads `Actor-Verified: none`, since nobody was verified at that moment; yours reads `access`.
5. **Stop** (`stop`). The first device that does not end rotated and persisted stops the run: the rest are not reached, and Needs attention raises a critical row naming the device and the stage. It clears when a later run (Rotate due devices now, once you have settled the device) finishes without a failure; until then the timer starts no run. A run that reaches the backup window stops there too, the rest left for the next run.
6. **Record** (`record`). Every run, including one refused, is a row in `scheduled_rotation_runs.jsonl` in the data folder: what it rotated, what it skipped and why, what failed and where, what it did not reach. Credentials › Profiles shows the last one.

A scheduled rotation changes nothing a manual one does not: no template, no shared profile, no enable secret.
