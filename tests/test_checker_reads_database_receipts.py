"""C635: the secret-storage checker scans the receipts where they are. After a move to the
records database a receipt is written there and the files keep what they held at the move, so
the checker reads each network's lines through `records_migrate.table_lines` (replaced here at
its edge: no database is reached) and asks the positional question it asks of the files.

- not on the database: the section says so and finds nothing;
- on it: a clean network is counted clean; a line carrying a secret in its slot is a finding
  named by network, the value printed nowhere; a network whose lines cannot be read is
  UNPROVEN, never clean.
"""

import importlib.machinery
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = "snmp-server community Leaky-Comm-4471 RO"
LEAK = {"device": "r2", "program": [RAW]}


def _clean():
    """A line as the receipts writer stores it: masked by `redact_text` (`rows_for`)."""
    from modules.redact import redact_text
    masked = redact_text(RAW)
    assert masked != RAW, "the fixture's line holds no secret, so this proves nothing"
    return {"device": "r1", "program": [masked]}


def _checker():
    return importlib.machinery.SourceFileLoader(
        "nmas_check_secret_storage_db",
        os.path.join(ROOT, "scripts", "nmas-check-secret-storage")).load_module()


def test_the_checker_runs_the_section_and_counts_its_findings():
    """Parsed, not matched as text: `main()` adds the section's findings to its failures."""
    import ast
    with open(os.path.join(ROOT, "scripts", "nmas-check-secret-storage"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    adds = [n for n in ast.walk(main) if isinstance(n, ast.AugAssign)
            and isinstance(n.target, ast.Name) and n.target.id == "failures"
            and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
            and n.value.func.id == "database_receipts_section"]
    assert len(adds) == 1


def test_not_on_the_database_finds_nothing(monkeypatch, capsys):
    monkeypatch.setattr("modules.nsot.receipts.on_database", lambda: False)
    assert _checker().database_receipts_section(read=lambda n: [LEAK], networks=["Lab"]) == []
    assert "not in use" in capsys.readouterr().out


def test_on_the_database_each_network_is_scanned(monkeypatch, capsys):
    monkeypatch.setattr("modules.nsot.receipts.on_database", lambda: True)
    lines = {"Clean": [_clean()], "Leaky": [_clean(), LEAK]}

    def read(name):
        if name == "Broken":
            raise RuntimeError("the database did not answer")
        return lines[name]
    found = _checker().database_receipts_section(read=read,
                                                 networks=["Clean", "Leaky", "Broken"])
    out = capsys.readouterr().out
    assert found == ["Leaky's receipts in the database hold something in a secret position",
                     "Broken's receipts in the database could not be scanned: the database "
                     "did not answer"]
    assert "Clean: 1 line(s), no secret-shaped content" in out
    assert "Leaky-Comm-4471" not in out, "a finding names the network, never the value"
