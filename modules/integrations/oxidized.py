"""Oxidized (oxidized-web REST) integration (Phase 0: connection test only)."""

from modules.integrations.base import IntegrationClient
from modules.secrets_store import get_secret
from modules.settings_schema import get_setting


class OxidizedIntegration(IntegrationClient):
    name = "oxidized"
    label = "Oxidized"
    url_key = "oxidized_url"
    secret_keys = ("oxidized_password",)
    plain_keys = ("oxidized_username", "oxidized_node_identity", "oxidized_verify_tls")

    def session(self):
        s = super().session()
        user = get_setting("oxidized_username", "")
        if user:
            s.auth = (user, get_secret("oxidized_password"))
        return s

    def test_connection(self) -> dict:
        r = self._get("nodes.json")
        if not r["ok"]:
            return r
        try:
            nodes = r["response"].json()
            return {"ok": True, "message": f"{len(nodes)} node(s)"}
        except Exception:
            return {"ok": True, "message": "Connected"}

    def monitor(self) -> dict:
        """Per-device last fetch status and time.

        This is the backup half of "version control": a device Oxidized has
        stopped fetching stops appearing in history, and nothing else in the
        GUI says so.
        """
        r = self._get("nodes.json")
        if not r["ok"]:
            return r
        try:
            nodes = r["response"].json()
        except Exception as exc:              # noqa: BLE001
            return {"ok": False, "error": f"unreadable response: {exc}"}

        rows, failing = [], 0
        for node in nodes if isinstance(nodes, list) else []:
            status = (node.get("status") or "").lower()
            good = status == "success"
            failing += 0 if good else 1
            rows.append({
                "text": node.get("name") or node.get("ip") or "?",
                "value": (node.get("time") or "never")[:19],
                "state": "up" if good else "down",
                "note": "" if good else (status or "no fetch recorded"),
            })
        rows.sort(key=lambda row: (row["state"] == "up", row["text"]))
        return {
            "ok": True,
            "metrics": [
                {"label": "nodes", "value": str(len(rows))},
                {"label": "failing", "value": str(failing),
                 "state": "down" if failing else "up"},
            ],
            "detail": rows,
        }

    # ── read client ─────────────────────────────────────────────────────────
    #
    # Phase 0 shipped `test_connection()` only. These two are the read half,
    # and they exist for one question: **is Oxidized's copy of a device the
    # approved one**. A redeploy replays Oxidized's copy into a startup
    # config, so a change nobody approved becomes what the device boots.
    #
    # One HTTP call per device against Oxidized's own index, versus an SSH
    # session per device. This is the cheapest drift source in the stack.

    def fetch_config(self, node: str) -> dict:
        """The config Oxidized currently holds for *node*, verbatim.

        ``{"ok": True, "config": "...", "node": node}``.

        **Verbatim matters.** The caller normalises with the same comparator a
        restore baseline uses; normalising here would put a second, private
        copy of that policy in the transport layer, and the two would drift.

        An empty body is a **refusal**, not an empty config: Oxidized answers
        200 with nothing for a node it has never successfully fetched, and
        "the device has no configuration" is a claim this client is in no
        position to make.
        """
        if not (node or "").strip():
            return {"ok": False, "error": "no node name given"}
        r = self._get(f"node/fetch/{node}")
        if not r["ok"]:
            return {"ok": False, "node": node, "error": r["error"]}
        try:
            text = r["response"].text
        except Exception as exc:               # noqa: BLE001
            return {"ok": False, "node": node, "error": f"unreadable body: {exc}"}
        if not (text or "").strip():
            return {"ok": False, "node": node,
                    "error": ("Oxidized returned an empty body — it has no "
                              "successful fetch stored for this node")}
        return {"ok": True, "node": node, "config": text}

    def node_times(self) -> dict:
        """``{node name: last-fetch time}`` from Oxidized's own index.

        The **time half** of the freshness comparison. It is deliberately a
        single call for the whole fleet rather than one per device: the
        comparison asks about every device at once, and N calls are N chances
        to answer about a fleet that moved underneath them.

        A node Oxidized has never fetched is **absent from the mapping**, not
        present with a blank — an unknown time and an epoch are different
        facts, and only one of them lets a caller decide which copy is newer.
        """
        r = self._get("nodes.json")
        if not r["ok"]:
            return {"ok": False, "error": r["error"]}
        try:
            nodes = r["response"].json()
        except Exception as exc:               # noqa: BLE001
            return {"ok": False, "error": f"unreadable response: {exc}"}
        times = {}
        for node in nodes if isinstance(nodes, list) else []:
            name = node.get("name") or node.get("ip") or ""
            stamp = (node.get("time") or "").strip()
            if name and stamp:
                times[name] = stamp
        return {"ok": True, "times": times}
