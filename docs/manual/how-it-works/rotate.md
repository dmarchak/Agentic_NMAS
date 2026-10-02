# Rotate a credential

Rotation replaces the password the tool uses to sign in to one device with a new one the tool generates, records it, and then makes the device keep it across a reload. It is the riskiest operation in the tool, so the order of the steps is the lockout defence: the old session stays open until the new password is proven, only a failed proof undoes the change, and every state between "the device changed" and "the tool holds the new password" is named and recoverable.

![Rotation: the preview reads the account's line from the device and sends nothing; the apply stages a generated password on the tool's host, sends the new account line on a held session, proves it on a fresh login (a failed proof puts the old line back on the held session), records it in the credential store, the inventory and one commit, then runs the persistence chain: the device's own save first, then the lab's Oxidized and startup-file stages.](diagrams/rotate.svg)

You start it from the device's page (Rotate credential…). The same implementation also runs on the host as `nmas-rotate-credential`.

## The preview

1. **Preflight** (`preflight`). Read: whether the root-owned Oxidized helper is installed, matches the repository's copy and may run without a password (lab integration: on an installation without it, the rotation is refused here); the device's inventory row; its manifest identity; its committed golden; and the account's `username` line read live from the device (`show running-config | include ^username <account>`). Sent: nothing that changes the device (one read on a session that is closed again). Recorded: nothing. The program depends on whether the account holds a `secret` or a `password` on the device now, not in a stored capture, and each check is drawn by name as a gate; any one failing refuses the rotation before anything changes.
2. **The program is shown**. Read: nothing more. Sent: nothing. Recorded: nothing. It is the exact program for this device, the new password masked: one line (`username <account> privilege <n> algorithm-type scrypt secret <generated>`) when the account holds a secret, or `no username <account>` first and then that line when it holds a password, because the device refuses a secret over a password entry. Beside it are who else signs in as this account and what happens to each.
3. **The fingerprint**. Read: nothing more. Sent: nothing. Recorded: nothing. You confirm the plan's fingerprint, which binds the account's line and its entry kind; the apply computes it again and refuses a different one with nothing sent.

## The apply

The apply runs as a job, holding the device from start to finish, so no other operation can touch it meanwhile. The window can close; the in-flight panel shows it, and its result is read by its job id when it finishes. It runs as you: the job carries your verified identity into its thread.

1. **Preflight and confirmation, again** (`preflight`, `confirmation`). Read: everything the preview read, including the live account line. Sent: nothing. Recorded: nothing. A plan that moved since you confirmed refuses with nothing sent.
2. **Generate** (`generate`). Read: nothing. Sent: nothing. Recorded: nothing. A 32-character password is generated from a character set the Oxidized router.db format can carry.
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
13. **Persist** (see [Persist](persist#the-host-chain)). Read and Sent: as that chain says. Recorded: a persist row. The device page's rotation runs the whole host chain: the device's own save and read-back first, then the Oxidized and lab startup-file stages (lab integration). On an installation without the lab, those stages fail and the rotation ends "rotated, persistence unverified" even though the device itself is saved.

## The outcomes

The result names one state, with its one next step:

- **rotated and persisted**: export the break-glass record again;
- **rotated, persistence not yet attempted**: persist it from the device's page, then export the break-glass record;
- **rotated, persistence unverified**: a stage of the persistence chain stopped (the result names it). Do not reload the device; fix the stage and run `nmas-persist-credential` for it;
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

The break-glass record holds the old password, so the result's next step is a new break-glass export.
