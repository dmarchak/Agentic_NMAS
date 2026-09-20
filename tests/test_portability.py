"""Portability: Windows development, headless Linux deployment.

Constraint 5. Covers the Jenkins step shell, the TFTP root, and the fact that
importing a config module must not create directories.
"""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestJenkinsStepShell:
    def test_defaults_to_bat(self, monkeypatch):
        """Existing pipelines must regenerate unchanged."""
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: default)
        from modules import jenkins_shell
        assert jenkins_shell.step_shell() == "bat"
        assert jenkins_shell.null_device() == "NUL"

    def test_default_install_step_is_byte_identical(self, monkeypatch):
        """This is the exact string every generator used to hardcode."""
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: default)
        from modules import jenkins_shell
        assert jenkins_shell.install_deps_step() == (
            "bat 'pip install netmiko --quiet 2>NUL || echo netmiko already installed'"
        )

    def test_default_python_step_is_byte_identical(self, monkeypatch):
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: default)
        from modules import jenkins_shell
        assert jenkins_shell.python_step(
            "modules/check_runner.py", "--validate-all --list-slug lab"
        ) == "bat 'python modules\\\\check_runner.py --validate-all --list-slug lab'"

    def test_sh_mode_emits_posix(self, monkeypatch):
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: "sh")
        from modules import jenkins_shell
        assert jenkins_shell.step_shell() == "sh"
        assert jenkins_shell.null_device() == "/dev/null"
        assert jenkins_shell.script_path("modules/check_runner.py") == "modules/check_runner.py"
        assert "2>/dev/null" in jenkins_shell.install_deps_step()

    def test_invalid_setting_falls_back_to_bat(self, monkeypatch):
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: "powershell")
        from modules import jenkins_shell
        assert jenkins_shell.step_shell() == "bat"

    def test_settings_failure_falls_back_to_bat(self, monkeypatch):
        """Pipeline generation must never break because settings are unreadable."""
        def boom(*a, **kw):
            raise RuntimeError("settings unavailable")
        monkeypatch.setattr("modules.settings_schema.get_setting", boom)
        from modules import jenkins_shell
        assert jenkins_shell.step_shell() == "bat"


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

    def test_ensure_tftp_root_is_explicit(self, monkeypatch, tmp_path):
        from modules import config
        target = tmp_path / "tftp"
        monkeypatch.setattr(config, "TFTP_ROOT", str(target))
        assert not target.exists()
        assert config.ensure_tftp_root() == str(target)
        assert target.is_dir()

    def test_ensure_tftp_root_survives_unwritable_path(self, monkeypatch):
        """An unusable TFTP path must warn, not raise."""
        from modules import config
        monkeypatch.setattr(config, "TFTP_ROOT", "/proc/nonexistent/tftp")
        assert config.ensure_tftp_root() == "/proc/nonexistent/tftp"

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
