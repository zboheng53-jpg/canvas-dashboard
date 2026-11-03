import socket
import threading

import pytest

from deploy import oj_vpn_gateway
import settings
import tongji_oj_client


@pytest.fixture
def gateway():
    server = oj_vpn_gateway.Gateway(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.mark.parametrize("payload", [
    b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com\r\n\r\n",
    b"CONNECT oj.tongji.edu.cn:80 HTTP/1.1\r\n\r\n",
    b"CONNECT oj.tongji.edu.cn.evil.test:443 HTTP/1.1\r\n\r\n",
    b"GET http://oj.tongji.edu.cn/ HTTP/1.1\r\n\r\n",
])
def test_gateway_rejects_unapproved_targets(gateway, payload):
    with socket.create_connection(gateway.server_address, timeout=2) as client:
        client.sendall(payload)
        assert client.recv(1024).startswith((b"HTTP/1.1 403", b"HTTP/1.1 400"))


def test_gateway_tunnels_approved_host(gateway, monkeypatch):
    one, two = socket.socketpair()
    called = []

    def connect(address, timeout):
        called.append(address)
        return one

    monkeypatch.setattr(oj_vpn_gateway.socket, "create_connection", connect)
    client = socket.socket()
    client.settimeout(2)
    client.connect(gateway.server_address)
    with client, two:
        client.sendall(b"CONNECT oj.tongji.edu.cn:443 HTTP/1.1\r\n\r\n")
        assert client.recv(1024).startswith(b"HTTP/1.1 200")
        client.sendall(b"hello")
        assert two.recv(5) == b"hello"
        two.sendall(b"world")
        assert client.recv(5) == b"world"
    assert called == [("oj.tongji.edu.cn", 443)]


def test_oj_session_uses_dedicated_proxy_without_environment_fallback(monkeypatch):
    monkeypatch.setattr(settings, "TONGJIOJ_VPN_PROXY_URL", "http://127.0.0.1:18080")
    session = tongji_oj_client._oj_session()
    assert session.trust_env is False
    assert session.proxies == {"http": "http://127.0.0.1:18080", "https": "http://127.0.0.1:18080"}


@pytest.mark.parametrize("url", ["http://evil.example:18080", "http://user:pass@localhost:123", "https://127.0.0.1:80", "http://127.0.0.1:123/path"])
def test_oj_session_rejects_nonlocal_or_invalid_proxy(monkeypatch, url):
    monkeypatch.setattr(settings, "TONGJIOJ_VPN_PROXY_URL", url)
    with pytest.raises(ValueError):
        tongji_oj_client._oj_session()
