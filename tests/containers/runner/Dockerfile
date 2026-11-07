# The container harness's check runner (test-only, never shipped): Mercury's own code reading the
# harness's Ryu from inside the internal network, since an internal network publishes no port to
# the host (measured 2026-11-07, Docker 29.1.3: `docker port` lists nothing for a container whose
# only network is internal). Python 3.12, CI's interpreter's minor version. Every package is one
# Mercury already installs, at requirements.lock's version, so the runner adds no licence.
FROM python:3.12-slim
RUN pip install --no-cache-dir \
        requests==2.34.2 urllib3==2.0.7 idna==3.19 charset-normalizer==3.5.1 \
        certifi==2023.11.17 PyYAML==6.0.1 \
        pytest==9.1.1 pluggy==1.6.0 iniconfig==2.3.0 packaging==24.0 pygments==2.17.2 \
 && useradd --uid 10002 --no-create-home --shell /usr/sbin/nologin runner
USER 10002
WORKDIR /src
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/src
ENTRYPOINT ["python", "-m", "pytest", "-p", "no:cacheprovider", "--noconftest", \
            "--rootdir", "/src"]
CMD ["tests/containers/harness_checks.py"]
