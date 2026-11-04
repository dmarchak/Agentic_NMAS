# The local CI runner's job image (docs/LOCAL_CI.md, "The runner image"; the operator's answer
# 2, 2026-11-03): act's medium Ubuntu 24.04 image, pinned by digest, with Firefox and geckodriver
# added for the browser tests, each pinned by version and checked against its published sha256.
# GitHub's ubuntu-24.04 image carries both; act's medium image does not.
#
# Built by the host step (docs/LOCAL_CI.md, section 11), never at run time:
#   docker build -t nmas-local-ci-runner:<this file's sha256, first 12> -f runner.Dockerfile <empty folder>
# and the platform act runs is the built image's ID, pinned by digest (NMAS_LOCAL_CI_PLATFORM).
#
# The pins, read 2026-11-03 from each project's own release metadata:
# - BASE: catthehacker/ubuntu:act-24.04's index digest on Docker Hub (built 2026-08-15, image
#   version 20260815; 567 MB compressed, 6 layers, amd64);
# - Firefox 158.0.1 (released 2026-10-20): its sha256 from Mozilla's SHA256SUMS for the release;
# - geckodriver 0.37.1 (released 2026-07-20): its sha256 from the GitHub release asset's digest.
# Firefox and geckodriver are the versions the laptop's gate runs its browser tests with.
ARG BASE=catthehacker/ubuntu@sha256:c58e2b364da03b0c804c7d660f2ecbedf2f221a382b9baa0b344b0144780ff43
FROM ${BASE}

ARG FIREFOX_VERSION=158.0.1
ARG FIREFOX_SHA256=dce45470139242cf294eb6ada3d192a9bb334696842b02b71ade448a139eb41a
ARG GECKODRIVER_VERSION=0.37.1
ARG GECKODRIVER_SHA256=e815130ea95983e162ae91843b48d3a3ce991735635fce83a647afde21e09f7e

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]

# iproute2: scripts/nmas-test brings loopback up inside the suite's namespace with `ip`, which
# GitHub's image carries and act's medium image does not (measured 2026-11-03: "ip: not found").
# Firefox's shared libraries (its Linux tarball links GTK 3 and ALSA), and fonts for pages drawn
# in the browser tests.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl xz-utils iproute2 \
      libgtk-3-0t64 libasound2t64 libx11-xcb1 libxtst6 libdbus-glib-1-2 \
      fonts-dejavu-core fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

RUN d="$(mktemp -d)" \
 && curl -fsSL --max-time 900 -o "$d/firefox.tar.xz" \
      "https://ftp.mozilla.org/pub/firefox/releases/${FIREFOX_VERSION}/linux-x86_64/en-US/firefox-${FIREFOX_VERSION}.tar.xz" \
 && echo "${FIREFOX_SHA256}  $d/firefox.tar.xz" | sha256sum -c - \
 && tar -xJf "$d/firefox.tar.xz" -C /opt \
 && ln -s /opt/firefox/firefox /usr/local/bin/firefox \
 && curl -fsSL --max-time 300 -o "$d/geckodriver.tar.gz" \
      "https://github.com/mozilla/geckodriver/releases/download/v${GECKODRIVER_VERSION}/geckodriver-v${GECKODRIVER_VERSION}-linux64.tar.gz" \
 && echo "${GECKODRIVER_SHA256}  $d/geckodriver.tar.gz" | sha256sum -c - \
 && tar -xzf "$d/geckodriver.tar.gz" -C /usr/local/bin geckodriver \
 && rm -r "$d" \
 && firefox --version && geckodriver --version | head -1

LABEL org.opencontainers.image.title="nmas-local-ci-runner" \
      org.opencontainers.image.description="act's medium Ubuntu 24.04 runner image with Firefox and geckodriver, for the local CI runner (docs/LOCAL_CI.md)"
