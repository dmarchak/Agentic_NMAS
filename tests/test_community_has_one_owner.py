"""C139 / C141: the SNMP community has ONE owner, each device's own secret.

Measured on the host 2026-09-28: no list had a `collector_config.json`, so
`get_snmp_community()` returned its literal fallback, and `snmp_get`,
`snmp_walk` and `get_device_summary` defaulted to the same literal: the
fleet's real community, in a public repository. The code's default WAS the
configuration. Now NMAS reads the device's own secret (the one intent renders
from), per device, so the state between two devices' rotations is simply two
devices holding different values. No fallback, anywhere.

The resolver (`modules/collector_config.py`) and its one caller, the agent's SNMP poll, left
with the AI family (D15, 2026-10-14), and their tests with them. What stays is the rule over
every function: no parameter named for a community has a default.
"""

import ast
import os

from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestNoDefaultAnywhere:
    FILES = ("modules", "routes", "app.py")

    def _sources(self):
        for base in self.FILES:
            path = os.path.join(ROOT, base)
            if os.path.isfile(path):
                yield path
                continue
            yield from tracked(path, suffix=".py")

    def test_no_parameter_named_community_has_a_default(self):
        found, scanned = [], 0
        for path in self._sources():
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    scanned += 1
                    args = node.args.args + node.args.kwonlyargs
                    defaults = ([None] * (len(node.args.args) - len(node.args.defaults))
                                + list(node.args.defaults) + list(node.args.kw_defaults))
                    for a, dflt in zip(args, defaults):
                        if "community" in a.arg and dflt is not None:
                            found.append(f"{os.path.relpath(path, ROOT)}:{node.name}({a.arg})")
        assert scanned > 1000, scanned
        assert found == [], found

    def test_the_planted_default_is_found(self):
        """The control: the scan sees the shape it forbids."""
        tree = ast.parse('def snmp_get(host, oids, community="x"): pass')
        fn = tree.body[0]
        assert fn.args.args[2].arg == "community" and fn.args.defaults
