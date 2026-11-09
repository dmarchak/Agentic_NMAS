"""of_versions 1.0.0: the controller's OpenFlow version pin as a managed app (C2670; the SDN
platform design revision 6, section 10, "the deploy channel": loaded first). A Ryu 4.34 app
written for Python 3.5, the oldest controller interpreter measured, and parsing as 3.9, the
controller's (r7, section 11c.6). Its logic is `of_versions_logic`; this module is the wiring:

- **the pin:** `OFP_VERSIONS` is OpenFlow 1.0 and 1.3, so the controller offers no version a
  switch's platform profile refuses (C2593, C2598; the manifest's `openflow_versions`, which
  Mercury's conformance check reads before any deploy);
- **switch connect and leave** (`EventOFPStateChange`): the version each switch negotiated is
  kept, so `/health` shows it (and says so if one is ever outside the pin);
- **REST** (under `/of_versions`): `GET /health`, `{"ok", "problems", ...}`, read by Mercury's
  post-check after every deploy.

It installs no flow, reads no config and reaches nothing.
"""

import json

from ryu.app.wsgi import ControllerBase, Response, WSGIApplication, route
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import DEAD_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_0, ofproto_v1_3

import of_versions_logic as logic

NAME = "of_versions"
VERSION = "1.0.0"
PREFIX = "/" + NAME


class OfVersions(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION, ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {"wsgi": WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(OfVersions, self).__init__(*args, **kwargs)
        self.negotiated = {}            # dpid -> wire version
        self.datapaths = {}             # dpid -> datapath
        kwargs["wsgi"].register(OfVersionsRest, {"versions_app": self})

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change(self, ev):
        dp = ev.datapath
        if dp.id is None:
            return
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
            self.negotiated[dp.id] = dp.ofproto.OFP_VERSION
            self.logger.info("%s: switch %d negotiated OpenFlow %s", NAME, dp.id,
                             logic.version_text(dp.ofproto.OFP_VERSION))
        elif ev.state == DEAD_DISPATCHER and self.datapaths.get(dp.id) is dp:
            del self.datapaths[dp.id]
            self.negotiated.pop(dp.id, None)

    def health(self):
        out = logic.health(self.negotiated)
        out.update({"app": NAME, "version": VERSION})
        return out


class OfVersionsRest(ControllerBase):
    """The app's REST, under PREFIX (the manifest's `rest`)."""

    def __init__(self, req, link, data, **config):
        super(OfVersionsRest, self).__init__(req, link, data, **config)
        self.app = data["versions_app"]

    @route(NAME, PREFIX + "/health", methods=["GET"])
    def health(self, req, **_kwargs):
        return Response(status=200, content_type="application/json", charset="utf-8",
                        body=json.dumps(self.app.health(), sort_keys=True).encode("utf-8"))
