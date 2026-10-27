# The lab's Ryu controller (lab environment, not product: PHASE8_PLAN 17.6). Ryu 4.34 needs
# Python 3.9; Ubuntu 24.04's 3.12 breaks its dependencies. The pins: setuptools<58 and pip<24
# install Ryu's setup, eventlet 0.30.2 still has the ALREADY_HANDLED Ryu imports (0.31 removed
# it). The build checks the pins itself (its last RUN step). Built and run on the laptop
# 2026-10-26: ryu-manager 4.34, REST on 127.0.0.1:8080 only, OpenFlow on 0.0.0.0:6653.
FROM python:3.9-slim
RUN pip install --no-cache-dir "setuptools<58" "pip<24" \
 && pip install --no-cache-dir --no-build-isolation "eventlet==0.30.2" "ryu==4.34"
COPY l4_switch_13.py /opt/lab/l4_switch_13.py
RUN ryu-manager --version \
 && python -c "import ryu.app.ofctl_rest, ryu.app.rest_topology, ryu.topology.switches, ryu.app.simple_switch_13; print('imports ok')"
EXPOSE 6653 8080
# REST on loopback only: Mercury reads it on the same host; OpenFlow listens on every address
# and the host's firewall admits the Mininet VM alone (the run uses host networking, so ufw's
# rules apply to it).
# Topology from the controller (the operator, 2026-10-27; PHASE8_PLAN 17.1 S14): OpenFlow switches
# run no LLDP, so Ryu discovers links itself (--observe-links: LLDP sent by packet-out, read back by
# packet-in) and serves them, with switches and hosts, on ryu.app.rest_topology's
# /v1.0/topology/{switches,links,hosts}.
ENTRYPOINT ["ryu-manager", "--ofp-tcp-listen-port", "6653", "--wsapi-host", "127.0.0.1", \
            "--wsapi-port", "8080", "--observe-links", \
            "ryu.app.ofctl_rest", "ryu.app.rest_topology", "/opt/lab/l4_switch_13.py"]
