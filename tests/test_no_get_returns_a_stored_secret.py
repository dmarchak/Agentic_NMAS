"""B11's claim, over the whole population of stores: no GET returns a secret.

P.3 step 6's sweep (`test_p3_secrets_write_only.py`) planted two values, the
Anthropic key and the NetBox token, and swept the argument-FREE GETs. So its
claim was scoped to a population it had defined itself, and register C55
lived outside it: `GET /monitoring/config` returned both SNMP communities,
from a store (`lists/*/collector_config.json`) that neither the sweep nor
`nmas-check-secret-storage` knew about. The proxy-population rule, inside
the check built to catch leaks.

**The population here is a SURVEY, not the stores somebody remembered**
(2026-09-27, the operator's question: is the collector config the last?):
* the checker's `secret` class under `data/`, which classifies every file:
  settings secrets, credential profiles, overrides and template secrets,
  device passwords in `devices.csv`, and now the collector config;
* `.env` (the Anthropic key);
* every store holding device CONFIGURATION, which carries secrets in config
  syntax: goldens, backups, the approval queue's diffs, chat histories (tool
  results), and the config cache;
* the CSV-era variable store, which returns whatever it holds.

Each store gets a DISTINCT planted value. EVERY GET is called, with its
arguments filled by the planted objects' own names (an argument-free sweep
cannot reach `/golden/version/<host>`; `/download_backup/<file>` was one until today's
Backups left at 7.8, C632, and its files stay planted as an install's residue), twice:
* as an ANONYMOUS caller: no planted value may come back;
* as a verified PERSON: only a reveal-gated route (audited, by design) may
  return one.

`STORES` is compared against the checker's secret classes, so a secret store
the checker learns about and this sweep does not plant fails here.
"""

import contextlib
import json
import os
import re
import shutil
import socket
import subprocess

import pytest

DEVICE = {"hostname": "r1", "ip": "192.0.2.1"}
LIST = "Default"


def _p(tag):
    """A planted value: long, distinct, and unmistakable in any body."""
    return f"PLANTED{tag}Zq7x"


#: store -> the values planted in it. Filled by `planted` below.
#: The AI family's own stores (chat history, config cache, variables, tool cache) left with
#: it (D15, 2026-10-14). The collector config and the trap buffer outlive their code as files
#: an install may still hold, so they stay planted as that residue.
STORES = ("env", "settings", "credential_profile", "device_override",
          "template_secret", "devices_csv", "collector_config", "golden",
          "backup", "approval_queue", "snmp_traps", "legacy_devices_csv",
          "legacy_golden")

#: The checker's `secret` patterns, each mapped to the store planted for it.
#: A pattern the checker gains without a plant here fails the test below.
CHECKER_SECRET_CLASSES = {
    "key.key": None, "secret.key": None,       # keys, never content a route reads
    "user_settings.json": "settings", "user_settings.json.*": None,
    "jenkins_checks.json": None,               # retired (P.4): nothing reads it
    "credential_profiles.json": "credential_profile",
    "credential_profiles.json.*": None,
    "lists/*/devices.csv": "devices_csv", "lists/*/devices.csv.*": None,
    "lists/*/collector_config.json": "collector_config",
    "lists/*/collector_config.json.*": None,
    # Found by deriving the population from the code's writers (2026-09-27).
    "snmp_traps.json": "snmp_traps", "lists/*/snmp_traps.json": "snmp_traps",
    "Devices.csv": "legacy_devices_csv",
}

#: GETs a verified person may use to see a secret: reveal-gated and audited.
REVEALS = {"/onboard/bootstrap/<hostname>"}

#: {rule: reason} GETs found returning a planted value, not yet fixed. Only
#: shrinks; each is register C56, found by this sweep's first run.
KNOWN_LEAKS = {}
# Empty since C56 was fixed (2026-09-27): the four it named, plus the trap
# buffer found by deriving the stores from the code, are masked on the way
# out. An entry here is a register finding.
KNOWN_LEAKS_CEILING = 0


def _config_body(tag):
    return (f"hostname r1\n"
            f"username admin privilege 15 secret 9 {_p(tag + 'Sec')}\n"
            f"snmp-server community {_p(tag + 'Comm')} RO\n"
            f"end\n")


def plant_backup(list_name, tag, stamp="20261001_000000"):
    """A backup file as today's removed Backups wrote one (`<host>_<ip>_running_<stamp>.cfg`
    in the list's backups folder), written straight to the file; its name."""
    from modules import config

    folder = os.path.join(config.list_data_path(list_name), "backups")
    os.makedirs(folder, exist_ok=True)
    name = f"r1_{DEVICE['ip']}_running_{stamp}.cfg"
    with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
        fh.write(_config_body(tag))
    return name


@pytest.fixture(scope="module")
def planted(tmp_path_factory):
    """Plant every store, sweep every GET inside the planting (so the GETs'
    known writes, C33, land before the store is restored), and restore."""
    with planted_stores() as values:
        values["_anon"] = _sweep(values, person=False)
        values["_person"] = _sweep(values, person=True)
        yield values


@contextlib.contextmanager
def planted_stores():
    """Plant every store in the harness store, and restore it afterwards.
    Shared with the POST sweep (C77), which is the same population of stores
    driven through a different population of routes."""
    from modules import config

    mp = pytest.MonkeyPatch()
    store = config.DATA_DIR
    original = os.path.join(os.path.dirname(store), os.path.basename(store) + ".b11")
    shutil.copytree(store, original)
    mp.setattr(socket.socket, "connect",
               lambda *a, **k: (_ for _ in ()).throw(OSError("tests do not touch a network")))
    values = {}
    try:
        import app as A
        from modules import approval_queue, credentials, device, secrets_store
        from modules.nsot import repo as R

        A.app.test_client().get("/v2/")
        values["env"] = [_p("Env")]
        mp.setenv("ANTHROPIC_API_KEY", _p("Env"))

        values["settings"] = []
        for key in secrets_store.SECRET_KEYS:
            v = _p("Set" + key.replace("_", ""))
            config.set_user_setting(key, secrets_store.encrypt_value(v))
            values["settings"].append(v)

        credentials.save_profile("planted-profile", "admin", _p("ProfPw"), _p("ProfSec"))
        values["credential_profile"] = [_p("ProfPw"), _p("ProfSec")]
        credentials.set_device_override(DEVICE["ip"], "admin", _p("OvrPw"))
        values["device_override"] = [_p("OvrPw")]
        credentials.set_template_secret(
            credentials.template_secret_key(LIST, "r1", "snmp_ro"), _p("Tmpl"))
        values["template_secret"] = [_p("Tmpl")]

        csv_path = os.path.join(config.list_data_path(LIST), "devices.csv")
        device.write_devices_csv([dict(DEVICE, device_type="cisco_ios", username="admin",
                                       password=device.fernet.encrypt(_p("DevPw").encode()).decode(),
                                       secret=device.fernet.encrypt(_p("DevSec").encode()).decode())],
                                 csv_path)
        values["devices_csv"] = [_p("DevPw"), _p("DevSec")]

        # No code writes a community here any more (C139: its one owner is
        # each device's own secret). An install that set one before still
        # holds it in the file, so it is planted as that residue, written
        # straight to the file, and no route may return it.
        coll = os.path.join(config.list_data_path(LIST), "collector_config.json")
        with open(coll, "w", encoding="utf-8") as fh:
            json.dump({"snmp_community_ro": _p("CollRo"),
                       "snmp_community_rw": _p("CollRw")}, fh)
        values["collector_config"] = [_p("CollRo"), _p("CollRw")]

        R.save_golden(LIST, [R.GoldenItem("r1", _config_body("Gold"), DEVICE["ip"])],
                      allow_new=True)
        values["golden"] = [_p("GoldSec"), _p("GoldComm")]

        # Today's Backups left at 7.8 (C632); its folder outlives the code as files an
        # install may still hold, so it is planted as that residue, in the shape the
        # removed writer named its files, and no route may return it.
        values["_backup_file"] = plant_backup(LIST, "Back")
        values["backup"] = [_p("BackSec"), _p("BackComm")]

        approval_queue.add_approval("update_golden_config", "planted", DEVICE["ip"], "r1",
                                    diff="+" + _config_body("Queue").replace("\n", "\n+"))
        values["approval_queue"] = [_p("QueueSec"), _p("QueueComm")]

        # The trap buffer's file, as the receiver (gone with the AI family, D15) left it.
        with open(os.path.join(config.DATA_DIR, "snmp_traps.json"), "w",
                  encoding="utf-8") as fh:
            json.dump([{"id": "planted", "source_ip": DEVICE["ip"], "community": _p("Trap"),
                        "version": "v2c", "summary": "planted trap", "varbinds": []}], fh)
        values["snmp_traps"] = [_p("Trap")]
        legacy = os.path.join(config.DATA_DIR, "Devices.csv")
        device.write_devices_csv([dict(DEVICE, hostname="legacy", device_type="cisco_ios",
                                       username="admin",
                                       password=device.fernet.encrypt(_p("LegPw").encode()).decode(),
                                       secret="")], legacy)
        values["legacy_devices_csv"] = [_p("LegPw")]
        # The deprecated golden store (C77's sweep, 2026-09-27): read-only,
        # still read by `_find_golden_config_file()` for a device the manifest
        # does not know, and holding whole configs. Neither sweep planted it.
        legacy_dir = os.path.join(config.list_data_path(LIST), "golden_configs")
        os.makedirs(legacy_dir, exist_ok=True)
        with open(os.path.join(legacy_dir, "legacy9.cfg"), "w", encoding="utf-8") as fh:
            fh.write("! Golden config -- legacy9 (192.0.2.9)\n" + _config_body("LegG"))
        values["legacy_golden"] = [_p("LegGSec"), _p("LegGComm")]
        yield values
    finally:
        mp.undo()
        shutil.rmtree(store, ignore_errors=True)
        shutil.copytree(original, store)
        shutil.rmtree(original, ignore_errors=True)


def _fill(rule, values):
    names = {"hostname": "r1", "host": "r1", "device": "r1", "ip": DEVICE["ip"],
             "filename": values["_backup_file"], "list_name": LIST, "list": LIST,
             "name": "planted-profile", "path": "cisco_ios/base.j2",
             "rel_path": "cisco_ios/base.j2", "tool": "grafana"}
    url = rule.rule
    for arg in rule.arguments:
        value = names.get(arg, "zz")
        url = re.sub(r"<(?:[a-z]+:)?%s>" % arg, value, url)
    return url + f"?list_name={LIST}&session_id=main&limit=50"


def _sweep(values, person):
    import app as A
    from modules import identity

    mp = pytest.MonkeyPatch()
    if person:
        who = identity.Identity(actor="test-person@example.invalid",
                                email="test-person@example.invalid", kind="person",
                                verified=True, outcome="ok", peer="198.51.100.7",
                                peer_trusted=True, header_present=True)
        mp.setattr(identity, "identify", lambda _r: who)
    else:
        mp.setattr(identity, "identify", lambda _r: identity.Identity(
            peer="198.51.100.7"))
    planted = {v: store for store, vs in values.items() if not store.startswith("_")
               for v in vs}
    hits, swept = [], []
    try:
        client = A.app.test_client()
        for rule in sorted(A.app.url_map.iter_rules(), key=lambda r: r.rule):
            if "GET" not in (rule.methods or ()) or rule.endpoint == "static":
                continue
            swept.append(rule.rule)
            try:
                body = client.get(_fill(rule, values)).get_data(as_text=True)
            except Exception:                  # noqa: BLE001
                continue                       # a crash returns nothing to leak
            hits += [(rule.rule, store) for v, store in planted.items() if v in body]
    finally:
        mp.undo()
    return sorted(set(hits)), swept


class TestThePopulation:
    def test_every_surveyed_store_was_planted(self, planted):
        missing = [s for s in STORES if not planted.get(s)]
        assert missing == [], f"planted nothing in: {missing}"

    def test_the_checker_s_secret_classes_are_all_accounted_for(self):
        """A secret store the checker learns about and this sweep does not
        plant is the C55 gap again, one store over."""
        import importlib.machinery
        import importlib.util

        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "scripts", "nmas-check-secret-storage")
        loader = importlib.machinery.SourceFileLoader("nmas_check_secret_storage", path)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(mod)
        secret = {pat for pat, kind in mod.DATA_CLASSES if kind == "secret"}
        assert secret == set(CHECKER_SECRET_CLASSES), sorted(secret ^ set(CHECKER_SECRET_CLASSES))
        assert {s for s in CHECKER_SECRET_CLASSES.values() if s} <= set(STORES)


class TestNoGetReturnsAStoredSecret:
    def test_anonymous(self, planted):
        hits, swept = planted["_anon"]
        assert len(swept) >= 100, len(swept)       # 104 GETs measured
        new = [h for h in hits if h[0] not in KNOWN_LEAKS]
        assert new == [], f"a GET returned a planted secret to an ANONYMOUS caller: {new}"

    def test_person_only_through_a_reveal(self, planted):
        hits, _ = planted["_person"]
        new = [h for h in hits if h[0] not in REVEALS and h[0] not in KNOWN_LEAKS]
        assert new == [], f"a GET returned a planted secret outside a reveal: {new}"

    def test_the_sweep_can_see_a_leak(self, planted):
        """The control: a route that returns a planted value is found."""
        import flask

        probe = flask.Flask("probe")
        value = planted["collector_config"][1]

        @probe.route("/leak")
        def leak():
            return {"x": value}

        assert value in probe.test_client().get("/leak").get_data(as_text=True)

    def test_the_leak_list_only_shrinks(self):
        assert len(KNOWN_LEAKS) == KNOWN_LEAKS_CEILING

    def test_no_ghosts(self, planted):
        anon, _ = planted["_anon"]
        person, _ = planted["_person"]
        still = {r for r, _ in anon + person}
        ghosts = sorted(set(KNOWN_LEAKS) - still)
        assert ghosts == [], f"no longer leaks: remove from KNOWN_LEAKS: {ghosts}"


class TestEveryFileTheCodeWritesIsClassified:
    """The operator's question after C55: are there other stores outside the
    sweep? "The checker would have said" only covers files that EXIST on the
    host it runs on, which is how collector_config.json was missed (never
    written on the deployment). So the population is derived from the CODE:
    every file name the code joins onto the data directory or a list's
    directory must fall in one of the checker's classes. Its first run found
    nine, including the trap buffer, which stores each trap's community."""

    #: Names the scan finds that are classified through a subdirectory, or
    #: live outside data/, each with where.
    EXPLAINED = {
        "index.json": "lists/*/playbooks/index.json (covered by lists/*/playbooks/*)",
        "deferred.json": "update/deferred.json, the Update page's wait for CI: target, "
                         "person, time, host-step hashes (covered by update/*)",
        "deferred_outcome.json": "update/deferred_outcome.json, how that wait ended "
                                 "(covered by update/*)",
    }

    def _writers(self):
        from tests.source_index import tracked

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        names = {}
        files = (tracked("modules", suffix=".py", root=root)
                 + tracked("routes", suffix=".py", recursive=False, root=root)
                 + [os.path.join(root, "app.py")])
        for f in files:
            text = open(f, encoding="utf-8").read()
            for m in re.finditer(r"""["']([\w.-]+\.(?:json|jsonl|csv|log|key))["']""", text):
                ctx = text[max(0, m.start() - 200):m.start()]
                if re.search(r"DATA_DIR|list_data|data_dir", ctx):
                    names.setdefault(m.group(1), set()).add(os.path.relpath(f, root))
        return names

    def test_floor(self):
        names = self._writers()
        # The collector config and the trap buffer left the list with their writers (the AI
        # family, D15, 2026-10-14); they stay planted above as files an install may hold.
        assert {"user_settings.json", "credential_profiles.json", "deploy_audit.jsonl",
                "acknowledgements.jsonl"} <= set(names), sorted(names)

    def test_every_written_name_is_classified(self):
        import fnmatch
        import importlib.machinery
        import importlib.util

        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "scripts", "nmas-check-secret-storage")
        loader = importlib.machinery.SourceFileLoader("nmas_check_secret_storage2", path)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(mod)
        pats = [p for p, _ in mod.DATA_CLASSES]
        missing = sorted(n for n in self._writers() if n not in self.EXPLAINED
                         and not any(fnmatch.fnmatch(c, p) for c in (n, f"lists/x/{n}")
                                     for p in pats))
        assert missing == [], f"written under data/ and in no class: {missing}"
