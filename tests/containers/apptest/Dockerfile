# The container harness's app test image (C2854; test-only, never shipped): the harness's
# controller image, Ryu 4.34 on the network's own controller Python (build argument PYTHON,
# major.minor, no default: scripts/nmas-harness passes it), with pytest added at the version
# measured for that Python and pinned in the same constraints file (tests/containers/ryu/
# constraints-<PYTHON>.txt, already in the controller image at /etc/harness/constraints.txt).
# An app's listed tests run here, never in Mercury's process or its job sandbox (the operator's
# decision C2635, 2026-11-07), by modules/apps/test_run.py, which starts each run in a fresh
# container with no network, every capability dropped, no-new-privileges, a read-only root and
# the app's folder and the app SDK mounted read-only.
ARG PYTHON
FROM mercury-harness-ryu:4.34-py${PYTHON}
ARG PYTHON
USER root
RUN pip install --no-cache-dir -c /etc/harness/constraints.txt pytest \
 && python -m pytest --version \
 && python -c "import pytest, sys; pins = dict(l.strip().split('==') for l in open('/etc/harness/constraints.txt') if '==' in l and not l.startswith('#')); sys.exit(0 if pytest.__version__ == pins['pytest'] else 'pytest ' + pytest.__version__ + ' is not the pin ' + pins['pytest'])"
USER 10001
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python", "-B", "-m", "pytest", "-p", "no:cacheprovider"]
