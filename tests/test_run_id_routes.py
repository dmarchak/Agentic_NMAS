"""C785: a route that takes a run id answers a malformed one with 404, never a 500. The walk of
every v2 page after the AI family's deploy (2026-10-14) found three answering 500 to 'r1':
`reads.get` raised `ValueError: not a run id` inside the view. The id's shape is now part of
the URL (`<run_id:...>`, `reads.url_converter`), so an id of any other shape matches no route.
The population is every rule with an argument named `run_id`, read from the app's own map."""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def app():
    import app as nmas
    return nmas.app


def _run_id_rules(app):
    return [r for r in app.url_map.iter_rules() if "run_id" in r.arguments]


class TestEveryRunIdIsShapedInTheUrl:
    def test_every_route_taking_a_run_id_uses_the_converter(self, app):
        from modules.nsot import reads
        rules = _run_id_rules(app)
        assert len(rules) >= 4, [r.rule for r in rules]   # Show commands' three, the Test's one
        loose = [r.rule for r in rules
                 if type(r._converters["run_id"]).regex != reads.RUN_ID]
        assert loose == [], f"takes a run id of any shape: {loose}"

    @pytest.mark.parametrize("bad", ["r1", "../x", "20261014T000000000Z-abc"])
    def test_a_malformed_id_is_404_on_every_one(self, app, bad):
        client = app.test_client()
        for rule in _run_id_rules(app):
            url = rule.rule.replace("<network>", "Default").replace("<run_id:run_id>", bad)
            method = "post" if "POST" in rule.methods and "GET" not in rule.methods else "get"
            resp = getattr(client, method)(url)
            assert resp.status_code == 404, (rule.rule, bad, resp.status_code)

    def test_the_control_an_unshaped_route_raises(self, app):
        """The shape the converter prevents: the same read behind a plain `<run_id>` raises."""
        import flask

        from modules.nsot import reads
        probe = flask.Flask("probe")
        probe.testing = True                # raise, as the view does, rather than answer 500

        @probe.route("/run/<run_id>")
        def run(run_id):
            return {"run": reads.get("Default", run_id)}

        with pytest.raises(ValueError, match="not a run id"):
            probe.test_client().get("/run/r1")
