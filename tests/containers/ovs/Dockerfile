# The container harness's switch (the SDN platform design revision 6, section 15; test-only,
# never shipped): Open vSwitch from Ubuntu 24.04's own package (3.3.x, the lab's OVS hosts run
# 3.3.4), on its USERSPACE datapath only (datapath_type=netdev): no kernel module is loaded or
# needed, so the kernel datapath's GPLv2 code is never used (the operator, 2026-11-06). Its ports
# are OVS's own dummy and patch ports, so it needs no capability: the compose file drops them all.
FROM ubuntu:24.04
RUN apt-get update \
 && apt-get install -y --no-install-recommends openvswitch-switch \
 && rm -rf /var/lib/apt/lists/* \
 && ovs-vswitchd --version
COPY ovs-start /usr/local/bin/ovs-start
COPY bridges.conf /etc/harness/bridges.conf
ENTRYPOINT ["/bin/sh", "/usr/local/bin/ovs-start"]
