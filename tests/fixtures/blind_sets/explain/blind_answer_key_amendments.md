# Explain's blind answer key: amendments

The key itself (`blind_answer_key.md`, sha256
`ab0816a085747b43dde2a065e4961dd54adf9a83e32a9b93911dc7e87a114185`) is kept byte for byte as the
operator confirmed and locked it on 2026-10-29: its sha256 seeds the draw
(`scripts/nmas-blind-draw`), so an edit there would change which scenarios were drawn. Each
amendment is the operator's, dated, with its reason, written before any run of the case it
changes, and read with the key by whoever builds that case.

## A1 (the operator, 2026-11-02 ~20:3x UTC): B2, r8's heartbeat alert

**Scenario:** B2, alerts during a declared maintenance window (a Mercury Reload of r8).

**The case it governs:** r8's heartbeat-missing alert, whose evidence pack holds the Reload's
record and Mercury's own row that the reload ended unverified. The case builder left it out of
the first build (2026-11-02) because the key's row says "Person? No" with no alternative, against
that record. No run of this case had been made when this was written.

**The amendment:** for this alert, the expected outcome is **needs a person**. A correct answer
cites the unverified reload record and attributes the heartbeat gap to the planned reload. An
answer that says no person is needed while ignoring the unverified record fails.

**The reason (the operator's):** the rule of 2026-10-30, that a planned action's side effect needs
attention when it does not recover as expected. r8's reload ended unverified, Mercury raised its
own row, and the operator acted on it (Re-key, then Verify again, 2026-11-01).

**What it does not change:** B2's other cases (r8's SNMP alert, case 4 of the first build), whose
row in the key stands as written.
