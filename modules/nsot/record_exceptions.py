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


def exception_for(sha: str):
    """The known exception for a commit, or None. A full sha only: a prefix
    match is the weaker-match class this project keeps catching."""
    return EXCEPTIONS.get((sha or "").strip())
