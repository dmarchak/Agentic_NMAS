"""The harness's OpenFlow version pin: an app that offers 1.0 and 1.3 and does nothing else.

Ryu offers the intersection of its loaded apps' OFP_VERSIONS (ryu/base/app_manager.py, Ryu
4.34; C2593), and ofctl_rest and rest_topology alone offer 1.0 to 1.5, whose hello an EOS 4.17
switch refuses (C2598). Lab 9's team pins the same two versions with its own `of_versions.py`
(the network's code, not Mercury's); this stand-in is the harness's, so the harness runs without
the network's apps. Written to parse on Python 3.5, the oldest controller interpreter measured.
"""

from ryu.base import app_manager
from ryu.ofproto import ofproto_v1_0, ofproto_v1_3


class HarnessVersions(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION, ofproto_v1_3.OFP_VERSION]
