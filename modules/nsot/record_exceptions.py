"""Commits whose record is known to be wrong, by hash, and how.

History is not rewritten (the operator: a clear record beats a rewritten
history). A commit whose trailer is known to misstate what happened is listed
here instead, and a reader that draws the trailer draws the exception beside
it: the record says one thing, the table says what is known about it, and
neither is edited to agree with the other.

**The eleven rotation commits** (C104, measured on the deployment host
2026-09-27). `save_golden()` rewrote any `source` outside a fixed list to
`manual`, and credential rotation passes `rotation`, so every rotation that
has ever happened on the host is recorded `Source: manual`. Exactly eleven
commits there carry `Source: manual`, and all eleven are these; the code is
fixed (any lowercase slug is recorded as given). The ten commits there with no
`Source:` at all are a different fact (hand or pre-convention commits) and
are not listed: absent is not wrong.

**First goldens recorded as the agent: measured, and there are NONE** (C102,
2026-09-27). Auto-Create saved each first golden through
`_save_golden_config_file()`, whose defaults are `Source: ai` and
`Actor: ai-agent`, so a person's button would be recorded as an agent that has
never made a tool call. Refresh Hostnames re-saved goldens the same way.
Measured on the host: no commit carries `Source: ai`, `Actor: ai-agent` or
`Source: approval` (the same query finds all 18 `Source: pipeline` commits, so
it can see a trailer that is there), `default` is the host's only list, and
its first goldens came from the migration (all nine, 2026-09-20) and
onboarding. So Auto-Create's use, if any, predates the repository and wrote to
the legacy store. Nothing to list, and both paths are removed. An install
where these exist lists them here, by hash, the same way.

**The two baseline re-applies** (C70, measured on the host 2026-09-27).
The batch commit wrote `Source: pipeline` for a deploy and a restore alike,
so both restores on the host (the first run at 18:53 and the re-run at
23:45, found by their `re-apply` subject: exactly two) name the mechanism
rather than the workflow. The code is fixed: a restore records `restore`.

Any screen that states a claim about history (the Versions screen's "N of M
commits carry a verified identity", D10) draws these beside it.
"""

#: {full sha: exception}. The list the commits live in is recorded for the
#: reader; a sha is what identifies the commit.
EXCEPTIONS = {
    sha: {"list": "default", "field": "Source", "recorded": "manual",
          "was": "rotation", "finding": "C104",
          "why": ("recorded as manual because save_golden rewrote any source "
                  "outside a fixed list; this commit is a credential rotation")}
    for sha in (
        "e1e8e4971b166efedba32ad7de77aa2cc3ead562",  # s1, 2026-09-26
        "fc427b4d0a2b6fefbdd4d7cd189ad063336a9c06",  # r6
        "3d1fbf2912eeb8b7c9cee6dca6973cade2aca81b",  # s3
        "fc6f81e37ccbbe504d76f913abb53aaa695a0d37",  # s4
        "dd4ac3a58bbb95d1c4d50cc44afbc888dda67018",  # s2
        "04adeee56cef62ccdc17b13582b747145746d6f4",  # s1
        "940b7ed6bdbe73ba38a202bcafe18081302aa50a",  # r5
        "cc04b39f4b27e85586530f641b3eb98d6a774f8a",  # r4
        "85261c170d550456384ce41664727c494290c8a9",  # r3
        "5a548fe9d295d664c2aab284acfafcd57b6a1f24",  # r1
        "bf1166874a55f8e0cd9949de7f9a7177bb7e56fb",  # r2
    )
}

EXCEPTIONS.update({
    sha: {"list": "default", "field": "Source", "recorded": "pipeline",
          "was": "restore", "finding": "C70",
          "why": ("recorded as pipeline because the batch commit named the "
                  "mechanism for deploys and restores alike; this commit is a "
                  "baseline re-apply")}
    for sha in (
        "ed6548e3859f0135cefdb7a32e06618e39c0e28d",  # r2, 2026-09-27 18:53
        "6d8e722c89b24b3579930f8843d794492517a71c",  # r2, 2026-09-27 23:45
    )
})


def exception_for(sha: str):
    """The known exception for a commit, or None. A full sha only: a prefix
    match is the weaker-match class this project keeps catching."""
    return EXCEPTIONS.get((sha or "").strip())


# ---------------------------------------------------------------------------
# Withdrawn baselines: a restore point a person decided must never be re-applied
# ---------------------------------------------------------------------------

#: {full sha of the baseline's commit: the decision}. A baseline is a claim
#: that the network was right at that moment, and the newest one is the one
#: anyone would re-apply. Keyed on the COMMIT, so the record survives the tag's
#: deletion and the table can say what was there. The restore routes refuse a
#: withdrawn commit while its tag still exists; once the tag is gone, the
#: Baselines table draws the deletion in its place.
WITHDRAWN_BASELINES = {
    "e63b2e6d64f7b61dd116e0460b8913644ea2a056": {
        "list": "default", "tag": "baseline/20260927T154517Z", "finding": "C70",
        "decided": "2026-09-28", "by": "the operator",
        "why": ("it records r2 deliberately broken for C70 (OSPFv3 removed from "
                "GigabitEthernet2, load-interval 30 added), captured by Save All 30 s "
                "after the break. It was kept as the only record of the pre-restore "
                "state, and that reason expired when C70 finished. The commit stays "
                "in history; only the restore point is withdrawn"),
    },
}


def withdrawn_baseline(sha: str):
    """The withdrawal recorded for a baseline's commit, or None. Full sha only."""
    return WITHDRAWN_BASELINES.get((sha or "").strip())
