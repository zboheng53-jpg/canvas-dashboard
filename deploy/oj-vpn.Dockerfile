ARG BASE_IMAGE
FROM ${BASE_IMAGE}
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*
COPY motionpro.sh /tmp/motionpro.sh
RUN sh /tmp/motionpro.sh --nox11 && rm /tmp/motionpro.sh
COPY oj_vpn_gateway.py oj_vpn_supervisor.py /opt/oj-vpn/
ENTRYPOINT ["/bin/sh", "-c", "/usr/bin/vpnd >/dev/null 2>&1; service vpnmanager start >/dev/null 2>&1 || true; exec python3 /opt/oj-vpn/oj_vpn_supervisor.py"]
