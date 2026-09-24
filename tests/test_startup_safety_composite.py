"""*"Applies"* is a true answer to a different question, so the checker asks
presence first.

**Measured live, 2026-09-24.** `nmas-check-startup-applies r6` reported
**APPLIES** — *"the password form applies behind the injected line; the
device ends up with this credential"* — while r6's startup file held the
**bootstrap** credential. The statement is correct: a `password 0` form
genuinely does apply. What it means for r6 is *"this device will come back
on a credential NMAS does not hold"*, and the tool printed it green.

Inside `persist()` that is safe, because the presence stage runs first and
stops the chain. **Read directly, that ordering is not there** — and the
result was worse than the absent-file failure it replaced, *because that one
was loud and this one was green*.

**Eighth instance of the class tonight, and the second where a composite was
safe by an accident of ordering rather than by design.**

The fix is the checker, not the function: `verify_startup_applies()`'s
question is legitimate and its answer is correct. What was missing is that
nothing asked the presence question on this path.
"""

import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestPresenceOutranksApplicability:
    def test_the_checker_asks_both_and_presence_first(self):
        """Presence first, applicability second, both asked.

        **Parsed, not indexed**: the comment above the calls explains the
        defect and names `verify_startup_applies` first, so a string index
        finds the prose rather than the call. Sixth time tonight that a
        comment matched the thing it described.
        """
        import ast
        import importlib.util
        import inspect
        import textwrap
        from importlib.machinery import SourceFileLoader

        path = os.path.join(ROOT, "scripts", "nmas-check-startup-applies")
        spec = importlib.util.spec_from_file_location(
            "chk", path, loader=SourceFileLoader("chk", path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        tree = ast.parse(textwrap.dedent(inspect.getsource(mod.check_one)))
        order = [n.func.attr for n in ast.walk(tree)
                 if isinstance(n, ast.Call)
                 and getattr(n.func, "attr", "").startswith("verify_startup")]

        assert order, "the parse found neither call"
        assert order[0] == "verify_startup_carries_current", \
            f"applicability is asked first again: {order}"
        assert "verify_startup_applies" in order, "it stopped asking at all"

    def test_a_bootstrap_file_reads_NOT_SAFE_even_though_it_applies(self,
                                                                   monkeypatch):
        """**The control the operator named.** r6 in its current state."""
        from modules.nsot import credential_rotation as cr

        monkeypatch.setattr(cr, "_resolve_target", lambda *a, **k: {
            "host": "user@clab", "configs_dir": "labs/r6/configs",
            "launch_patch": "labs/r6/patches/p.py", "lab": "r6"})
        monkeypatch.setattr(cr, "_ssh_read", lambda h, c, **k: {
            "ok": True,
            "text": "hostname r6\nusername admin privilege 15 password 0 boot\n"})
        monkeypatch.setattr(cr, "_current_golden", lambda repo, host:
                            "hostname r6\n"
                            "username admin privilege 15 secret 9 $9$rotated\n")
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda ln: "/x")

        out = cr.verify_startup_carries_current("r6", list_name="Default")

        assert out["ok"] is False, "a bootstrap file read as carrying current"
        assert out["kind"] == "password"
        assert "credential NMAS does not hold" in out["reason"]

    def test_and_goes_green_once_the_file_carries_secret_9(self, monkeypatch):
        """**The floor, and the acceptance for the sync half** — the same
        test, which is what makes it worth having."""
        from modules.nsot import credential_rotation as cr

        rotated = "username admin privilege 15 secret 9 $9$rotated"
        monkeypatch.setattr(cr, "_resolve_target", lambda *a, **k: {
            "host": "user@clab", "configs_dir": "labs/r6/configs",
            "launch_patch": "labs/r6/patches/p.py", "lab": "r6"})
        monkeypatch.setattr(cr, "_ssh_read", lambda h, c, **k: {
            "ok": True, "text": f"hostname r6\n{rotated}\n"})
        monkeypatch.setattr(cr, "_current_golden", lambda repo, host:
                            f"hostname r6\n{rotated}\n")
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda ln: "/x")

        out = cr.verify_startup_carries_current("r6", list_name="Default")

        assert out["ok"] is True
        assert out["kind"] == "secret"
        assert "brings it back as it is now" in out["reason"]

    def test_no_golden_is_INCONCLUSIVE_not_a_pass(self, monkeypatch):
        """With nothing to compare against, *"the file holds a credential"*
        says nothing about whether it is the one NMAS can use."""
        from modules.nsot import credential_rotation as cr

        monkeypatch.setattr(cr, "_resolve_target", lambda *a, **k: {
            "host": "user@clab", "configs_dir": "labs/r6/configs",
            "launch_patch": "p", "lab": "r6"})
        monkeypatch.setattr(cr, "_ssh_read", lambda h, c, **k: {
            "ok": True,
            "text": "username admin privilege 15 secret 9 $9$x\n"})
        monkeypatch.setattr(cr, "_current_golden", lambda repo, host: "")
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda ln: "/x")

        out = cr.verify_startup_carries_current("r6", list_name="Default")

        assert out["ok"] is False
        assert out["inconclusive"] is True
        assert "not the same as it carrying it" in out["error"]


class TestTheFormIsAlwaysNamed:
    """*"Applies"* must never be printable without saying **what** applies —
    that is the whole distinction between the two questions."""

    def test_the_result_carries_the_line_it_found(self, monkeypatch):
        from modules.nsot import credential_rotation as cr

        monkeypatch.setattr(cr, "_resolve_target", lambda *a, **k: {
            "host": "h", "configs_dir": "d", "launch_patch": "p", "lab": "r6"})
        monkeypatch.setattr(cr, "_ssh_read", lambda h, c, **k: {
            "ok": True,
            "text": "username admin privilege 15 password 0 boot\n"})
        monkeypatch.setattr(cr, "_current_golden", lambda repo, host:
                            "username admin privilege 15 secret 9 $9$r\n")
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda ln: "/x")

        out = cr.verify_startup_carries_current("r6", list_name="Default")
        assert "password" in out["startup_line"]

    def test_but_never_the_VALUE(self, monkeypatch):
        """A checker that prints the hash has put the credential in a
        scrollback, and the question is which form applies."""
        from modules.nsot import credential_rotation as cr

        assert cr._redact_value(
            "username admin privilege 15 secret 9 $9$SECRETHASH") \
            == "username admin privilege 15 secret 9 <redacted>"
        assert cr._redact_value(
            "username admin privilege 15 password 0 PLAINTEXT") \
            == "username admin privilege 15 password 0 <redacted>"

    def test_the_printer_names_the_form(self):
        import os

        src = open(os.path.join(ROOT, "scripts",
                                "nmas-check-startup-applies"),
                   encoding="utf-8").read()
        assert "startup_line" in src
        assert "without saying what applies" in src

    def test_a_losing_presence_still_reports_what_applies_said(self):
        """So nobody reads the composite as a verdict on applicability it
        never reached."""
        import os

        src = open(os.path.join(ROOT, "scripts",
                                "nmas-check-startup-applies"),
                   encoding="utf-8").read()
        assert "true statement about a different question" in src
