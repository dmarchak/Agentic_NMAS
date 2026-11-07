# The container harness's controller (the SDN platform design revision 6, section 15; test-only,
# never shipped): Ryu 4.34 on the network's own controller Python, given as the build argument
# PYTHON (major.minor, no default: scripts/nmas-harness passes the network's recorded version).
# Each supported version has its measured constraints file, constraints-<PYTHON>.txt; a version
# without one fails the build at the COPY, naming the file.
ARG PYTHON
FROM python:${PYTHON}-slim
ARG PYTHON
COPY constraints-${PYTHON}.txt /etc/harness/constraints.txt
RUN pip install --no-cache-dir -c /etc/harness/constraints.txt pip setuptools \
 && pip install --no-cache-dir --no-build-isolation -c /etc/harness/constraints.txt \
        eventlet ryu \
 && ryu-manager --version \
 && python -c "import ryu.app.ofctl_rest, ryu.app.rest_topology, ryu.topology.switches" \
 && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin ryu
COPY ryu-start /usr/local/bin/ryu-start
USER 10001
EXPOSE 6653 8080
ENTRYPOINT ["/bin/sh", "/usr/local/bin/ryu-start"]
