# C1463: monitoring rules that reach Grafana without a person (design note, not built)

The register's row C1463: a device's monitoring rules reach Grafana only through a person.
That means re-measuring the heartbeat window, running `nmas-telemetry-rules` on the host, and
taking the root install step after every onboarding and every retirement (MANUAL_STEPS M11 to
M13). The row already carries route A's sizing; this note sets out its order and what each
step proves. Written 2026-10-24 by the overnight run, for the operator's review.

## Route A, in order

1. **Regenerate on the commit that changes the input.** The generators (`heartbeat_windows`,
   `telemetry_rules`) run from the same post-commit trigger as the Prometheus targets keeper.
   That trigger fires on a golden commit that changes a device's population or subscriptions,
   on an onboarding, and on a retirement. A new device gets a provisional heartbeat window
   (s5's, 2026-10-24, was one), and a scheduled re-measure replaces it, so M12 goes. Output:
   the rule documents, committed, with no install yet. About half a day.
2. **Install through Grafana's alerting provisioning API.** The rules go in with provenance
   `api`, no file and no restart, so no root step. Then they are read back, and job health
   gets a row saying whether the installed rules match the generated ones. About a day.
3. **One migration off the file-provisioned rules.** The root step runs one last time, then
   the files are removed. Rules installed through the API are Mercury's, read-only in
   Grafana's UI. About half a day with its walk.
4. **Tests, the manual's pages, the Monitoring card's words.** About half a day.

About 2.5 to 3 days in all.

## Decisions and secrets that are the operator's

- **A secret:** Mercury's Grafana token needs alert-rule provisioning rights. The operator
  grants them; the agent never sees the value.
- **A choice:** whether rules installed through the API (read-only in Grafana's UI) are
  acceptable, or whether a person must be able to edit a rule there. Route B, C1462's signed
  root helper, keeps the file route and is M to L.

## What makes a wrong one visible

- A device with no installed rule, or an installed rule that differs from the generated one,
  is a Needs attention row naming the device and the rule, and it clears when they match
  again.
- A retirement that leaves a rule behind fails `tests/test_retire_leaves_nothing.py`'s
  inventory: the rule is a per-device artefact.
