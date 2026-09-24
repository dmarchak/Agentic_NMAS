"""A regenerated self-signed certificate is not drift.

**Measured, 2026-09-24, both directions asked before deciding either.**

*Does anything depend on the certificate surviving a rebuild?* r1-r5 run
`restconf` with `ip http secure-server`, which uses it — so one must
**exist**. The yang-push subscriptions ride NETCONF over SSH and need none,
and nothing in this stack pins one. **It must exist and need not survive**,
which makes the sanitizer dropping it a *correct omission* rather than a
blind spot.

*Does the drift comparison report it?* **Yes.** A regenerated body and a new
`TP-self-signed-<chassis>` name produced three `only_left` and three
`only_right` lines through `configs_equivalent()`.

So every C8000v has carried a standing unexplained difference since the
2026-09-22 redeploy — r1, r2 and r4 logged *"yang-infra: ERROR: Failed to
create a new self-signed trustpoint"* and commit `758d1f56`'s **only**
changes were certificates. **Nobody saw it because the drift checker has
been off since 2026-08-30 — switched off three minutes after a run that
flagged all nine devices.**

That is the point of fixing it before the freshness comparison is built:
re-enabling drift, or adding a second comparison on the same comparator,
would flag every C8000v for something correct — *precisely the condition
that silenced the checker last time.* "Inherited, not designed" again, and
this one was waiting rather than acting.
"""

import pytest

BODY = "\n".join("  " + "0123456789ABCDEF" * 4 for _ in range(6))
GOLDEN = ("hostname r1\n"
          "crypto pki trustpoint TP-self-signed-2968666059\n"
          " enrollment selfsigned\n"
          "crypto pki trustpoint SLA-TrustPoint\n"
          " enrollment terminal\n"
          "crypto pki certificate chain TP-self-signed-2968666059\n"
          " certificate self-signed 01\n" + BODY + "\n  quit\n"
          "crypto pki certificate chain SLA-TrustPoint\n"
          " certificate ca 01\n"
          "end\n")
#: What the device holds after a rebuild: new body, new chassis-derived name.
REBUILT = GOLDEN.replace("0123456789ABCDEF", "FEDCBA9876543210") \
                .replace("2968666059", "3155120447")


class TestTheFilterIsNarrow:
    def test_the_devices_own_trustpoint_goes(self):
        from modules.nsot.normalize import strip_self_signed_certs

        out = strip_self_signed_certs(GOLDEN)
        assert not any("TP-self-signed" in line for line in out)

    def test_a_CA_SIGNED_trustpoint_stays(self):
        """**The floor, and the reason for the narrowness.** A CA-signed
        trustpoint is configuration somebody chose, and a change to it is
        real drift."""
        from modules.nsot.normalize import strip_self_signed_certs

        out = strip_self_signed_certs(GOLDEN)
        assert any("SLA-TrustPoint" in line for line in out)
        assert any("certificate ca 01" in line for line in out)

    def test_it_takes_the_indented_BODY_too(self):
        """`_strip()` matches line prefixes and a certificate chain is a
        stanza — header plus an indented body of hex."""
        from modules.nsot.normalize import strip_self_signed_certs

        out = strip_self_signed_certs(GOLDEN)
        assert not any("0123456789ABCDEF" in line for line in out)
        assert "  quit" not in out

    def test_and_stops_at_the_next_unindented_line(self):
        from modules.nsot.normalize import strip_self_signed_certs

        out = strip_self_signed_certs(GOLDEN)
        assert "hostname r1" in out
        assert "end" in out


class TestDriftNoLongerReportsIt:
    def test_a_rebuilt_device_is_equivalent_to_its_golden(self):
        from modules.nsot import roundtrip

        assert roundtrip.configs_equivalent(GOLDEN, REBUILT)["equal"] is True

    def test_a_REAL_change_alongside_it_is_still_drift(self):
        """**The floor.** A filter that swallowed the difference would make
        every comparison pass, which is the failure this project calls a
        gate that silently opens."""
        from modules.nsot import roundtrip

        changed = REBUILT.replace("hostname r1",
                                  "hostname r1\nntp server 203.0.113.1")
        out = roundtrip.configs_equivalent(GOLDEN, changed)

        assert out["equal"] is False
        assert any("ntp server" in line
                   for line in (out["only_right"] or []))

    def test_a_CA_signed_certificate_change_is_still_drift(self):
        """The narrowness, measured through the comparator rather than the
        filter."""
        from modules.nsot import roundtrip

        changed = REBUILT.replace("certificate ca 01", "certificate ca 02")
        assert roundtrip.configs_equivalent(GOLDEN, changed)["equal"] is False

    def test_without_the_filter_it_WOULD_have_been_drift(self):
        """The measurement that motivated this, kept so the finding does not
        have to be re-derived: the raw diff really does differ."""
        from modules.nsot import normalize

        left = normalize.strip_for_diff(GOLDEN)
        right = normalize.strip_for_diff(REBUILT)
        assert left != right, \
            "the strip already removed them, so this finding is stale"
        assert any("TP-self-signed" in line for line in left)
