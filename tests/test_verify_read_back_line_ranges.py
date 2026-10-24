"""Verify's read-back matches a `line` range the device prints split (C1541, O0).

r7's deploy (2026-10-22, 07:16:53Z) sent three lines under `line vty 0 4`; r7 prints
the range as `line vty 0`, `line vty 1` and `line vty 2 4`, and the read-back reported
all three "missing" although the device carries them, because each sent line was keyed
on its exact stanza chain. A line under a `line <type> <a> [<b>]` stanza is now read
back for each member a..b in whichever printed stanza covers it, and held only when
every member holds it.

The running text is r7's own, read masked on 2026-10-22 (it holds no secret); the
program is the one r7's deploy receipt records. Addresses play no part in this read-back
(no address is parsed, compared or stored), so the IPv6 parity rule has no case here
beyond an interface section that carries an IPv6 address and reads back as before."""

from modules.nsot import verify_scope as V

R7_LINES = """\
line vty 0
 logging synchronous
 login local
 transport input ssh
line vty 1
 logging synchronous
 login local
 length 0
 transport input ssh
line vty 2 4
 logging synchronous
 login local
 transport input ssh
"""

R7_PROGRAM = ["interface GigabitEthernet3", " no shutdown", "exit",
              "line vty 0 4", " logging synchronous", " login local",
              " transport input ssh", "exit"]


def test_the_floor_r7_prints_the_range_split_and_the_program_sends_it_whole():
    assert "line vty 0 4" not in R7_LINES and "line vty 2 4\n" in R7_LINES
    assert "line vty 0 4" in R7_PROGRAM


class TestASplitRange:
    def test_r7s_three_vty_lines_read_back_found(self):
        rb = V.read_back(R7_PROGRAM, R7_LINES)
        assert rb["missing"] == [], rb
        assert rb["checked"] == 3
        # `no shutdown` is the one skipped line: a `no` line reads back as an absence.
        assert [s["line"] for s in rb["skipped"]] == ["interface GigabitEthernet3 > no shutdown"]

    def test_a_member_lacking_the_line_is_a_miss_naming_that_member(self):
        running = R7_LINES.replace("line vty 1\n logging synchronous\n login local\n",
                                   "line vty 1\n logging synchronous\n")
        assert running != R7_LINES
        rb = V.read_back(R7_PROGRAM, running)
        assert rb["checked"] == 3
        assert rb["missing"] == ["line vty 0 4 > login local (missing on vty 1)"], rb

    def test_a_range_partly_uncovered_is_a_miss_naming_the_uncovered_members(self):
        running = R7_LINES.replace("line vty 2 4\n", "line vty 2 3\n")
        rb = V.read_back(R7_PROGRAM, running)
        assert rb["missing"] == [
            "line vty 0 4 > logging synchronous (no printed stanza covers vty 4)",
            "line vty 0 4 > login local (no printed stanza covers vty 4)",
            "line vty 0 4 > transport input ssh (no printed stanza covers vty 4)"], rb

    def test_both_a_lacking_and_an_uncovered_member_are_named(self):
        running = R7_LINES.replace("line vty 0\n logging synchronous\n login local\n",
                                   "line vty 0\n logging synchronous\n")
        running = running.replace("line vty 2 4\n", "line vty 2 3\n")
        rb = V.read_back(["line vty 0 4", " login local", "exit"],
                         running)
        assert rb["missing"] == [
            "line vty 0 4 > login local (missing on vty 0; no printed stanza covers vty 4)"]

    def test_another_line_type_does_not_cover_a_member(self):
        running = R7_LINES.replace("line vty 2 4\n", "line aux 2 4\n")
        rb = V.read_back(["line vty 0 4", " login local", "exit"], running)
        assert rb["missing"] == ["line vty 0 4 > login local (no printed stanza covers "
                                 "vty 2, 3, 4)"]

    def test_the_line_held_under_the_wrong_member_is_still_a_miss(self):
        """`length 0` is under vty 1 only: vty 0, 2, 3 and 4 lack it."""
        rb = V.read_back(["line vty 0 4", " length 0", "exit"], R7_LINES)
        assert rb["missing"] == ["line vty 0 4 > length 0 (missing on vty 0, 2, 3, 4)"]


class TestACombinedRange:
    """The program sends members one by one; the device prints one range over them."""

    COMBINED = ("line vty 0 4\n logging synchronous\n login local\n"
                " transport input ssh\nline vty 5 15\n login local\n")

    def test_a_member_the_device_prints_inside_a_wider_range_reads_back(self):
        rb = V.read_back(["line vty 1", " login local", " transport input ssh", "exit"],
                         self.COMBINED)
        assert rb["missing"] == [] and rb["checked"] == 2

    def test_a_member_range_spanning_two_printed_stanzas_reads_back(self):
        rb = V.read_back(["line vty 3 7", " login local", "exit"], self.COMBINED)
        assert rb["missing"] == [] and rb["checked"] == 1

    def test_a_member_whose_wider_range_lacks_the_line_is_a_miss(self):
        rb = V.read_back(["line vty 3 7", " transport input ssh", "exit"], self.COMBINED)
        assert rb["missing"] == ["line vty 3 7 > transport input ssh (missing on vty 5, 6, 7)"]


class TestUnchangedBehaviour:
    CON = "line con 0\n logging synchronous\n stopbits 1\nline aux 0\n" + R7_LINES

    def test_line_con_0_held_reads_back(self):
        rb = V.read_back(["line con 0", " logging synchronous", "exit"], self.CON)
        # `unread` (C1646): the VLAN reads not made or not understood; a program with no VLAN
        # has none.
        assert rb == {"missing": [], "skipped": [], "checked": 1, "unread": []}

    def test_line_con_0_not_held_misses_as_it_always_has(self):
        rb = V.read_back(["line con 0", " exec-timeout 5 0", "exit"], self.CON)
        assert rb["missing"] == ["line con 0 > exec-timeout 5 0"]

    def test_an_unsplit_range_printed_as_sent_misses_as_it_always_has(self):
        running = "line vty 0 4\n login local\n"
        rb = V.read_back(["line vty 0 4", " login local", " length 0", "exit"], running)
        assert rb["missing"] == ["line vty 0 4 > length 0"] and rb["checked"] == 2

    def test_an_interface_section_reads_back_on_its_exact_chain(self):
        running = ("interface GigabitEthernet3\n ip address 192.0.2.1 255.255.255.0\n"
                   " ipv6 address 2001:DB8::1/64\n")
        program = ["interface GigabitEthernet3", " ip address 192.0.2.1 255.255.255.0",
                   " ipv6 address 2001:DB8::1/64", " description not-there", "exit"]
        rb = V.read_back(program, running)
        assert rb["checked"] == 3
        assert rb["missing"] == ["interface GigabitEthernet3 > description not-there"]

    def test_a_line_section_named_otherwise_is_matched_as_written(self):
        """`line 0/0/0` is not a <type> <a> [<b>] range: exact chain, as before."""
        running = "line 0/0/0\n login local\n"
        assert V.read_back(["line 0/0/0", " login local", "exit"], running)["missing"] == []
        assert V.read_back(["line 0/0/1", " login local", "exit"], running)["missing"] == [
            "line 0/0/1 > login local"]

    def test_the_skipped_reasons_are_kept_under_a_split_range(self):
        rb = V.read_back(["line vty 0 4", " no exec-timeout", " password 0 Zq7value",
                          "exit"], R7_LINES)
        assert rb["checked"] == 0 and rb["missing"] == []
        assert [s["why"] for s in rb["skipped"]] == [
            "a `no` line reads back as an absence",
            "a secret the device stores in another form"]
