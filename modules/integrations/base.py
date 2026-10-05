"""integrations/base.py

Shared base for every external-tool client.

Provides config load/save, a ``requests.Session`` with retry and timeout, a TLS
verify toggle, and a uniform ``{"ok": bool, "error": str, ...}`` result shape
matching the convention the rest of the codebase uses.

Constraint: every integration is optional. An unconfigured or unreachable tool
returns ``{"ok": False, "error": ...}``; it never raises into a request handler.
Nothing here is network-specific — all endpoints come from Settings.
"""

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from modules.secrets_store import get_secret, is_set, set_secret
from modules.settings_schema import get_setting

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 5.0


class IntegrationClient:
    """Base class for an external-tool client.

    Subclasses set :attr:`name`, :attr:`label`, :attr:`url_key`, and the
    ``*_KEYS`` tuples, then implement :meth:`test_connection`.
    """

    #: settings-key prefix, e.g. "prometheus"
    name: str = ""
    #: human-readable name for the UI
    label: str = ""
    #: settings key holding the base URL
    url_key: str = ""
    #: settings keys holding secrets (masked in the UI, encrypted at rest)
    secret_keys: tuple = ()
    #: non-secret settings keys this integration owns
    plain_keys: tuple = ()

    def __init__(self, timeout: float = DEFAULT_TIMEOUT, list_name: str = ""):
        self.timeout = timeout
        self._session = None
        #: The network this client is FOR (P.8 step 3): its settings resolve through
        #: `list_settings`. Empty is the installation's values, as before P.8.
        self.list_name = list_name or ""

    # ── configuration ───────────────────────────────────────────────────────

    def _setting(self, key: str, default=None):
        """A setting FOR this client's network: the one way a client reads its settings
        (tests/test_integrations_read_for_a_list.py refuses a direct read)."""
        if not self.list_name:
            return get_setting(key, default)
        from modules import list_settings

        return list_settings.value(self.list_name, key, default)

    def _secret(self, key: str, default: str = "") -> str:
        """A secret FOR this client's network, decrypted."""
        if not self.list_name:
            return get_secret(key, default)
        from modules import list_settings

        return list_settings.secret(self.list_name, key) or default

    @property
    def url(self) -> str:
        return (self._setting(self.url_key, "") or "").rstrip("/")

    @property
    def verify_tls(self) -> bool:
        return bool(self._setting(f"{self.name}_verify_tls", True))

    def is_configured(self) -> bool:
        """True when the integration has enough settings to attempt a call."""
        return bool(self.url)

    def get_config(self) -> dict:
        """Return this integration's settings, with secrets masked.

        Secret values never leave the process: the UI receives only a
        set/unset indicator.
        """
        cfg = {key: self._setting(key) for key in self.plain_keys}
        cfg[self.url_key] = self.url
        cfg["_secrets"] = {key: (bool(self._secret(key)) if self.list_name else is_set(key))
                           for key in self.secret_keys}
        cfg["_configured"] = self.is_configured()
        return cfg

    def save_config(self, values: dict) -> dict:
        """Persist submitted settings.

        A secret field submitted empty is left untouched, so a user editing an
        unrelated field on a masked form does not wipe a stored token.
        """
        from modules.config import set_user_setting

        if self.list_name:
            # FOR a network (P.8): its own store, the group rule and validation in one place.
            from modules import list_settings

            updates = {k: values[k] for k in self.plain_keys + (self.url_key,) if k in values}
            updates.update({k: values[k] for k in self.secret_keys if values.get(k)})
            self._session = None
            return list_settings.write(self.list_name, updates) if updates else {"ok": True}
        for key in self.plain_keys + (self.url_key,):
            if key in values:
                set_user_setting(key, values[key])
        for key in self.secret_keys:
            if values.get(key):
                set_secret(key, values[key])
        self._session = None      # force rebuild with new settings
        return {"ok": True}

    # ── HTTP ────────────────────────────────────────────────────────────────

    def _auth_headers(self) -> dict:
        """Override to supply Authorization headers."""
        return {}

    def session(self) -> requests.Session:
        """Return a retrying session. Built once, rebuilt after a config save."""
        if self._session is None:
            s = requests.Session()
            s.headers.update({"Accept": "application/json"})
            s.headers.update(self._auth_headers())
            s.verify = self.verify_tls
            retry = Retry(
                total=2,
                backoff_factor=0.3,
                status_forcelist=(500, 502, 503, 504),
                allowed_methods=("GET", "POST"),
            )
            s.mount("http://", HTTPAdapter(max_retries=retry))
            s.mount("https://", HTTPAdapter(max_retries=retry))
            self._session = s
        return self._session

    def _get(self, path: str, **params) -> dict:
        """GET *path* relative to the configured URL. Never raises."""
        if not self.is_configured():
            return {"ok": False, "error": "Not configured — set in Settings"}
        url = f"{self.url}/{path.lstrip('/')}"
        try:
            r = self.session().get(url, params=params or None, timeout=self.timeout)
            if r.status_code in (401, 403):
                # REFUSED, never "down" in general (P.21, C354): the service answered and
                # refused the tool's credential, so the fix is the credential, not the path.
                return {"ok": False, "status": r.status_code, "refused": True,
                        "error": f"HTTP {r.status_code}: {self.label} refused the tool's "
                                 "credential"}
            if r.status_code >= 400:
                return {"ok": False, "error": f"HTTP {r.status_code}", "status": r.status_code}
            return {"ok": True, "status": r.status_code, "response": r}
        except requests.exceptions.SSLError as exc:
            return {"ok": False, "error": f"TLS error: {exc}"}
        except requests.exceptions.ConnectionError:
            return {"ok": False, "error": f"Could not connect to {self.url}"}
        except requests.exceptions.Timeout:
            return {"ok": False, "error": f"Timed out after {self.timeout}s"}
        except Exception as exc:                      # noqa: BLE001 - never raise into a handler
            log.warning("%s: unexpected error calling %s: %s", self.name, path, exc)
            return {"ok": False, "error": str(exc)}

    # ── health ──────────────────────────────────────────────────────────────

    def test_connection(self) -> dict:
        """Probe the tool. Subclasses override with the tool's health endpoint."""
        return {"ok": False, "error": "test_connection not implemented"}

    def status(self) -> dict:
        """Badge state for the dashboard strip: green / red / grey."""
        if not self.is_configured():
            return {"ok": True, "state": "not_configured", "label": self.label,
                    "message": "Not configured — set in Settings"}
        result = self.test_connection()
        return {
            "ok": True,
            "state": ("up" if result.get("ok") else
                      "refused" if result.get("refused") else "down"),
            "label": self.label,
            "message": result.get("error") or result.get("message", "Connected"),
        }
