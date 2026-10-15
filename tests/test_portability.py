"""Portability: Windows development, headless Linux deployment.

Constraint 5. Covers the TFTP root and the fact that
importing a config module must not create directories.
"""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestTftpRoot:
    def test_import_does_not_create_tftp_root(self):
        """config.py used to os.makedirs(TFTP_ROOT) at import time.

        On Linux that created a literal directory named "C:" in the repo root,
        because the default was the Windows path "C:/TFTP-Root".
        """
        assert not (REPO_ROOT / "C:").exists(), (
            'A directory named "C:" exists in the repo root — the import-time '
            "makedirs of the Windows TFTP path has come back"
        )

    def test_default_is_os_appropriate(self):
        from modules import settings_schema
        default = settings_schema._default_tftp_root()
        if os.name == "nt":
            assert default.startswith("C:")
        else:
            assert default.startswith("/")

    def test_the_tftp_root_left_with_its_readers(self):
        """The TFTP root (`NMAS_TFTP_ROOT`, `tftp_root`) left with the device and bulk file
        routes, its last readers (D16, 2026-10-13; tag pre-remove/tftp-root). The setting is
        RETIRING for one release; nothing in the app reads or creates the folder."""
        from modules import config, settings_scope
        assert not hasattr(config, "TFTP_ROOT") and not hasattr(config, "ensure_tftp_root")
        assert settings_scope.SCOPES["tftp_root"][0] == settings_scope.RETIRING

    def test_no_hardcoded_tftp_server_ip(self):
        """The old default was one specific lab's address."""
        from modules import settings_schema
        assert settings_schema.DEFAULTS["tftp_server_ip"] == ""


class TestEnvironmentOverrides:
    @pytest.mark.parametrize("env,key,value,expected", [
        ("NMAS_PORT", "flask_port", "8080", 8080),
        ("NMAS_HOST", "flask_host", "127.0.0.1", "127.0.0.1"),
    ])
    def test_env_wins(self, monkeypatch, env, key, value, expected):
        from modules.config import _env_or_setting
        monkeypatch.setenv(env, value)
        default = 5000 if key == "flask_port" else "0.0.0.0"
        assert _env_or_setting(env, key, default) == expected

    def test_bad_int_env_falls_back(self, monkeypatch):
        from modules.config import _env_or_setting
        monkeypatch.setenv("NMAS_PORT", "not-a-number")
        assert _env_or_setting("NMAS_PORT", "flask_port", 5000) == 5000

    def test_headless_disables_browser(self):
        """NMAS_HEADLESS=1 must win over any stored setting."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c",
             "from modules.config import AUTO_OPEN_BROWSER; print(AUTO_OPEN_BROWSER)"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            env={**os.environ, "NMAS_HEADLESS": "1", "PYTHONPATH": str(REPO_ROOT)},
        )
        assert result.stdout.strip() == "False", result.stderr

    @pytest.mark.parametrize("env_value, expected", [(None, "True"), ("0", "False"),
                                                     ("1", "True")])
    def test_the_browser_is_the_environments_alone(self, tmp_path, env_value, expected):
        """C815 (the operator, 2026-10-15): a stored `auto_open_browser` is retiring and read by
        nothing; NMAS_AUTO_OPEN_BROWSER decides, on when unset."""
        import json
        import subprocess
        (tmp_path / "user_settings.json").write_text(json.dumps({"auto_open_browser": False}))
        env = {k: v for k, v in os.environ.items()
               if k not in ("NMAS_HEADLESS", "NMAS_AUTO_OPEN_BROWSER")}
        env.update(NMAS_DATA_DIR=str(tmp_path), PYTHONPATH=str(REPO_ROOT))
        if env_value is not None:
            env["NMAS_AUTO_OPEN_BROWSER"] = env_value
        result = subprocess.run(
            [sys.executable, "-c",
             "from modules.config import AUTO_OPEN_BROWSER; print(AUTO_OPEN_BROWSER)"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, env=env)
        assert result.stdout.strip() == expected, result.stderr
