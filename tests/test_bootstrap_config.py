"""Anything that reaches a CLI is ASCII, comments included.

The em dash has now broken this project twice, in two places that looked
unrelated:

1. a **pushed command** — ``description NSoT-managed b`` — where IOS consumed
   the first of three UTF-8 bytes, lost sync, and truncated the line. Netmiko
   reported an echo timeout, so the error named the symptom.
2. a **comment in a startup config** — ``! ... - management plane only`` —
   where vrnetlab typed the vIOS's config into its console line by line,
   waiting for a prompt after each. It hung on a line beginning ``!``, and the
   node never finished booting.

The same character, in a file, on a device, on both occasions. What made the
second one possible is that the fix for the first was attached to the *deploy
path*: ``assert_sendable`` ran on commands about to be pushed, and a startup
config is not a command list. But vrnetlab makes it one.

The C8000v booted the identical content without complaint, because it loads
its startup config as a file. So the property cannot be discovered by testing
one platform, and the rule cannot be "ASCII where we push". It is: **ASCII in
anything that reaches a CLI** — which on a console-replayed platform includes
every comment.
"""

import os

import pytest

from modules.nsot.bootstrap_config import (CONSOLE_REPLAYED,
                                           VRNETLAB_INJECTS_USER,
                                           UnsupportedPlatform,
                                           generated_secret, render_bootstrap,
                                           secret_clause)
from modules.nsot.deploy import UnsendableCommand

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = os.path.join(ROOT, "docs", "bootstrap-probe")


def _directives(text):
    """What the device actually acts on: every non-comment line.

    Bare ``!`` separators go too. The probe's C8000v file uses them inside its
    explanatory header, so keeping them would compare prose layout rather than
    configuration.
    """
    return [l for l in text.splitlines() if not l.startswith("!")]


class TestEveryGeneratedLineIsSendable:
    def test_the_iosxe_output_is_ascii(self):
        out = render_bootstrap("cisco_iosxe", hostname="r6", username="admin",
                               secret="abc12345")
        assert out.isascii()

    def test_the_ios_output_is_ascii(self):
        out = render_bootstrap("cisco_ios", hostname="s5", username="admin",
                               secret="abc12345")
        assert out.isascii()

    def test_a_non_ascii_hostname_is_refused(self):
        with pytest.raises(UnsendableCommand):
            render_bootstrap("cisco_iosxe", hostname="r—6", username="admin",
                             secret="abc12345")

    def test_a_non_ascii_secret_is_refused(self):
        """A generated secret is ASCII by charset; a supplied one is not."""
        with pytest.raises(UnsendableCommand):
            render_bootstrap("cisco_ios", hostname="s5", username="admin",
                             secret="pa—ss")

    def test_a_non_ascii_domain_is_refused(self):
        with pytest.raises(UnsendableCommand):
            render_bootstrap("cisco_iosxe", hostname="r6", username="admin",
                             secret="abc12345", domain="rcn–lab")

    def test_the_check_covers_comments_not_only_commands(self):
        """The exact gap the second em dash went through.

        A check applied to "the commands" and not to the whole artefact would
        pass a file whose only defect is in a comment — which is the file that
        hung a vIOS boot.
        """
        import inspect

        from modules.nsot import bootstrap_config

        source = inspect.getsource(bootstrap_config.render_bootstrap)
        body = source[source.index("text = "):]
        assert "assert_sendable(text.splitlines())" in body, (
            "the guard must run on the rendered text, not on a filtered "
            "subset of it")


class TestConsoleReplayedPlatformsCarryNoProse:
    """Every line costs a round trip, and is a chance to desync."""

    def test_vios_output_has_no_prose_comments(self):
        out = render_bootstrap("cisco_ios", hostname="s5", username="admin",
                               secret="abc12345")
        prose = [l for l in out.splitlines() if l.startswith("! ")]
        assert not prose, prose

    def test_bare_separators_are_still_allowed(self):
        """They are config-file furniture, not commentary, and IOS emits them
        itself — removing them would make the capture differ from the file."""
        out = render_bootstrap("cisco_ios", hostname="s5", username="admin",
                               secret="abc12345")
        assert "!" in out.splitlines()

    def test_iosxe_may_carry_prose_because_it_loads_a_file(self):
        out = render_bootstrap("cisco_iosxe", hostname="r6", username="admin",
                               secret="abc12345")
        assert any(l.startswith("! ") for l in out.splitlines())

    def test_ios_is_the_console_replayed_platform(self):
        assert "cisco_ios" in CONSOLE_REPLAYED
        assert "cisco_iosxe" not in CONSOLE_REPLAYED


class TestTheUsernameFormMatchesWhatThePlatformAccepts:
    """Measured on r2 in stage 1, and again on the probe.

    vrnetlab applies ``username admin privilege 15 password admin`` before the
    startup config on IOS-XE. A ``secret`` line for the same user is refused —
    "ERROR: Can not have both a user password and a user secret" — so the file
    would describe a credential the device does not have.
    """

    def test_iosxe_uses_the_password_form(self):
        assert secret_clause("cisco_iosxe", "x") == "password 0 x"

    def test_ios_uses_the_secret_form(self):
        assert secret_clause("cisco_ios", "x") == "secret 0 x"

    def test_only_iosxe_is_marked_as_injected(self):
        assert VRNETLAB_INJECTS_USER == {"cisco_iosxe"}


class TestItMatchesTheMeasuredProbeConfigs:
    """The probe measures what the wizard emits, or it measures nothing.

    Two files that happen to agree today are two files that will disagree
    later. These compare config lines — comments excluded, since the probe's
    C8000v file carries a long explanation of *why* it is shaped this way and
    a generated file should not.
    """

    def test_the_c8000v_shape_matches_bp_c8k(self):
        with open(os.path.join(PROBE, "configs", "bp-c8k.cfg"),
                  encoding="utf-8") as fh:
            measured = _directives(fh.read())
        generated = _directives(
            render_bootstrap("cisco_iosxe", hostname="bp-c8k",
                             username="admin", secret="admin"))
        assert generated == measured

    def test_the_vios_shape_matches_bp_vios(self):
        with open(os.path.join(PROBE, "configs", "bp-vios.cfg"),
                  encoding="utf-8") as fh:
            measured = _directives(fh.read())
        generated = _directives(
            render_bootstrap("cisco_ios", hostname="bp-vios",
                             username="admin", secret="admin"))
        assert generated == measured


class TestEveryProbeFileIsAscii:
    """The repository's own files, not only what the generator produces.

    These are hand-written and are fed to real nodes. ``bp-vios.cfg`` was not
    ASCII when it was committed, and nothing in the suite noticed until a node
    hung.

    Scoped to ``configs/`` — the files that reach a device. The topology YAML
    and the README are read by containerlab and by people; widening the rule
    to them would make it a house style rather than a safety property, and a
    rule that fires on prose is a rule people start ignoring.
    """

    def _files(self):
        for base, _dirs, names in os.walk(os.path.join(PROBE, "configs")):
            for name in names:
                yield os.path.join(base, name)

    def test_every_config_fed_to_a_node_is_ascii(self):
        offenders = []
        for path in self._files():
            with open(path, encoding="utf-8") as fh:
                for number, line in enumerate(fh, 1):
                    if not line.isascii():
                        bad = [c for c in line if not c.isascii()]
                        offenders.append(
                            f"{os.path.relpath(path, ROOT)}:{number} {bad!r}")
        assert not offenders, offenders

    def test_the_probe_directory_was_actually_found(self):
        """An empty walk would make the test above vacuously true."""
        assert len(list(self._files())) >= 3


class TestTheBootstrapSecretIsGenerated:
    def test_it_is_not_a_fixed_word(self):
        assert generated_secret() != generated_secret()

    def test_it_is_ascii_and_sendable(self):
        from modules.nsot.deploy import assert_sendable

        value = generated_secret()
        assert value.isascii()
        assert_sendable([f"username admin privilege 15 secret 0 {value}"])

    def test_it_survives_a_render(self):
        out = render_bootstrap("cisco_iosxe", hostname="r6", username="admin",
                               secret=generated_secret())
        assert out.isascii()


class TestAnUnknownPlatformIsRefusedNotGuessed:
    def test_it_raises(self):
        with pytest.raises(UnsupportedPlatform):
            render_bootstrap("arista_eos", hostname="x", username="a",
                             secret="bcdefghi")

    def test_the_message_says_to_measure(self):
        with pytest.raises(UnsupportedPlatform) as excinfo:
            render_bootstrap("juniper_junos", hostname="x", username="a",
                             secret="bcdefghi")
        assert "measuring" in str(excinfo.value)
        assert "bootstrap-probe" in str(excinfo.value)
