"""Secret-bearing files are created owner-only, by their creators.

Measured on the live install 2026-09-23: `.env` at 0644, world-readable, with
the Anthropic API key in it, for three weeks. `data/` at 0755 and every file
under it at 0644, including `key.key`.

**Nothing in the program had ever set a mode.** `os.makedirs()` and `open()`
take the process umask. So a `chmod` fixes one install and the next one is
born the same way — which is why these tests are on the creation sites rather
than on a runbook step.

`key.key` is tested first and separately: everything else is encrypted WITH
it, so a group-readable key means the ciphertext beside it was never
meaningfully protected. The encryption and the mode are one control, not two.
"""

import json
import os
import stat

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt",
                                reason="chmod cannot express owner-only on Windows")


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def _no_group_or_other(path):
    return not (_mode(path) & 0o077)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """A data directory the creators will build from scratch."""
    d = tmp_path / "data"
    monkeypatch.setattr("modules.config.DATA_DIR", str(d))
    monkeypatch.setattr("modules.config.KEY_FILE", str(d / "key.key"))
    monkeypatch.setattr("modules.config.USER_SETTINGS_FILE",
                        str(d / "user_settings.json"))
    return d


class TestTheKeyIsTheFloor:

    def test_secrets_store_creates_it_owner_only(self, data_dir, monkeypatch):
        from modules import secrets_store as ss

        monkeypatch.setattr(ss, "KEY_FILE", str(data_dir / "key.key"))
        monkeypatch.setattr(ss, "_fernet", None)
        ss._get_fernet()
        assert _mode(data_dir / "key.key") == 0o600

    def test_device_creates_it_owner_only(self, data_dir, monkeypatch):
        from modules import device

        monkeypatch.setattr(device, "KEY_FILE", str(data_dir / "key.key"))
        device.load_key()
        assert _mode(data_dir / "key.key") == 0o600

    def test_device_tightens_a_key_created_before_this_existed(self, data_dir,
                                                               monkeypatch):
        """The common case: an install whose key.key predates the fix."""
        from cryptography.fernet import Fernet

        from modules import device

        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / "key.key"
        path.write_bytes(Fernet.generate_key())
        os.chmod(path, 0o644)

        monkeypatch.setattr(device, "KEY_FILE", str(path))
        device.load_key()
        assert _no_group_or_other(path)

    def test_the_data_directory_is_owner_only(self, tmp_path):
        from modules.config import secure_dir

        d = secure_dir(str(tmp_path / "data"))
        assert _mode(d) == 0o700

    def test_an_existing_loose_directory_is_tightened(self, tmp_path):
        from modules.config import secure_dir

        d = tmp_path / "data"
        d.mkdir()
        os.chmod(d, 0o755)
        secure_dir(str(d))
        assert _no_group_or_other(d)


class TestEveryStoreCreatesItsFileOwnerOnly:

    def test_user_settings(self, data_dir, monkeypatch):
        from modules import config

        monkeypatch.setattr(config, "USER_SETTINGS_FILE",
                            str(data_dir / "user_settings.json"))
        config.save_user_settings({"tftp_root": "/srv/tftp"})
        assert _mode(data_dir / "user_settings.json") == 0o600

    def test_the_mode_is_applied_before_the_write(self, tmp_path):
        """Creating 0644 and chmod-ing after leaves a window in which the
        secret is on disk and world-readable -- the defect in miniature."""
        import inspect

        from modules import config

        src = inspect.getsource(config.open_secure)
        assert "os.open(path, flags, FILE_MODE)" in src

    def test_an_existing_loose_file_is_tightened_on_write(self, data_dir,
                                                          monkeypatch):
        from modules import config

        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / "user_settings.json"
        path.write_text("{}")
        os.chmod(path, 0o644)

        monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(path))
        config.save_user_settings({})
        assert _no_group_or_other(path)


def _checker():
    import importlib.util
    from importlib.machinery import SourceFileLoader

    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "scripts", "nmas-check-secret-storage")
    spec = importlib.util.spec_from_file_location(
        "chk", path, loader=SourceFileLoader("chk", path))
    chk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chk)
    return chk


class TestTheRetiredJenkinsStore:
    """P.4: nothing reads `jenkins_checks.json` any more, so a credential left
    in it has no owner. The checker names it until it is deleted."""

    def _run(self, data_dir, capsys):
        os.makedirs(data_dir, mode=0o700, exist_ok=True)
        _checker().main()
        return capsys.readouterr().out

    def test_a_present_file_is_named_as_retired(self, data_dir, capsys):
        data_dir.mkdir(mode=0o700)
        (data_dir / "jenkins_checks.json").write_text("{}")
        os.chmod(data_dir / "jenkins_checks.json", 0o600)
        assert "jenkins_checks.json is a RETIRED store" in self._run(data_dir, capsys)

    def test_an_absent_file_is_not(self, data_dir, capsys):
        """The floor: the finding is about the file, not printed regardless."""
        assert "RETIRED store" not in self._run(data_dir, capsys)


class TestTheCheckerGradesModes:

    def test_group_readable_is_a_failure(self, tmp_path):
        import importlib.util
        from importlib.machinery import SourceFileLoader

        # The script has no .py extension, so `spec_from_file_location`
        # cannot infer a loader and returns None. Naming the loader is what
        # makes an extensionless executable importable.
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "scripts", "nmas-check-secret-storage")
        spec = importlib.util.spec_from_file_location(
            "chk", path, loader=SourceFileLoader("chk", path))
        chk = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(chk)

        p = tmp_path / "f"
        p.write_text("x")
        os.chmod(p, 0o640)
        text, ok = chk._mode_verdict(str(p), 0o600)
        assert ok is False and "group" in text

        os.chmod(p, 0o600)
        _text, ok = chk._mode_verdict(str(p), 0o600)
        assert ok is True
