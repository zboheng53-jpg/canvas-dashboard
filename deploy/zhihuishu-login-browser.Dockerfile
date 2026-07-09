FROM mcr.microsoft.com/playwright/python:v1.59.0-jammy

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        openbox \
        x11vnc \
        xvfb \
        novnc \
        websockify \
    && rm -rf /var/lib/apt/lists/*

COPY deploy/zhihuishu-login-browser-entrypoint.sh /usr/local/bin/zhihuishu-login-browser
RUN chmod +x /usr/local/bin/zhihuishu-login-browser

ENV DISPLAY=:99
EXPOSE 6080

ENTRYPOINT ["/usr/local/bin/zhihuishu-login-browser"]
