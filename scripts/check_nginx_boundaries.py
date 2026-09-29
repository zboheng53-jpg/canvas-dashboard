"""Validate the deployment template with an isolated loopback nginx instance.

Run on Linux with nginx installed. Does not reload or edit the live configuration.
"""
from contextlib import ExitStack
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


class Upstream(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        type(self).requests.append((self.path, dict(self.headers)))
        if self.path.endswith("login-session-auth"):
            self.send_response(204 if self.headers.get("Cookie") == "session=fake-test-cookie" else 401)
        elif self.headers.get("Upgrade"):
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
        else:
            self.send_response(200)
            self.send_header("Set-Cookie", "container-cookie=blocked")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.do_GET()


def start_upstream(stack, port=0):
    server = ThreadingHTTPServer(("127.0.0.1", port), Upstream)
    stack.callback(server.server_close)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stack.callback(server.shutdown)
    return server.server_port


def range_upstream(stack, start):
    for port in range(start, start + 100):
        try:
            return start_upstream(stack, port)
        except OSError:
            continue
    raise RuntimeError("No isolated VNC test port available")


def check():
    with ExitStack() as stack, tempfile.TemporaryDirectory(prefix="dashboard-nginx-check-") as temp:
        root = Path(temp)
        assets = root / "assets"
        (assets / "built/js").mkdir(parents=True)
        (assets / "js").mkdir()
        (assets / "js/plain.js").write_text("plain")
        hashed = "built/js/test." + "a" * 20 + ".js"
        (assets / hashed).write_text("hashed")
        web = start_upstream(stack)
        zhs = range_upstream(stack, 6100)
        tji = range_upstream(stack, 6200)
        with socket.socket() as reserve:
            reserve.bind(("127.0.0.1", 0))
            port = reserve.getsockname()[1]
        source = (ROOT / "deploy/canvas-dashboard.nginx").read_text()
        source = source.replace("listen 80;", f"listen 127.0.0.1:{port};")
        source = source.replace("listen [::]:80;", "")
        source = source.replace("127.0.0.1:5000", f"127.0.0.1:{web}")
        source = source.replace("/home/ubuntu/canvas-dashboard/current/frontend/assets/", str(assets) + "/")
        config = root / "nginx.conf"
        config.write_text(f"pid {root}/nginx.pid; error_log {root}/error.log;\n"
            f"events {{ worker_connections 64; }}\nhttp {{ access_log off; client_body_temp_path {root}/body; "
            f"proxy_temp_path {root}/proxy; include /etc/nginx/mime.types;\n{source}\n}}")
        subprocess.run(["nginx", "-t", "-p", str(root), "-c", str(config)], check=True, capture_output=True)
        process = subprocess.Popen(["nginx", "-p", str(root), "-c", str(config), "-g", "daemon off;"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def stop():
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        stack.callback(stop)

        def request(path, headers=None, *, method="GET", length=None, body=None):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                if length is None:
                    connection.request(method, path, body=body, headers=headers or {})
                else:
                    connection.putrequest(method, path)
                    connection.putheader("Content-Length", str(length))
                    connection.endheaders()
                response = connection.getresponse()
                payload = response.read()
                return response.status, dict(response.getheaders()), payload
            finally:
                connection.close()
        for attempt in range(50):
            try:
                request("/healthz")
                break
            except OSError:
                if process.poll() is not None:
                    raise RuntimeError((root / "error.log").read_text())
                time.sleep(.1)
        Upstream.requests.clear()
        for path, content, cache in (("/static/js/plain.js", b"plain", "public, no-cache"),
                                     ("/static/" + hashed, b"hashed", "public, max-age=31536000, immutable")):
            status, headers, body = request(path)
            assert status == 200 and body == content, (path, status)
            assert headers["Cache-Control"] == cache, headers
            assert "javascript" in headers["Content-Type"], headers
        assert not Upstream.requests, "Static requests reached Web server"
        for obsolete in ("daily-english", "life-list"):
            for path in (f"/{obsolete}", f"/{obsolete}/", f"/{obsolete}/anything"):
                assert request(path)[0] == 410
        for platform, vnc_port in (("zhs", zhs), ("tji", tji)):
            path = f"/{platform}-vnc/{vnc_port}/fake_test_token_12345678/vnc.html"
            assert request(path)[0] == 401
            auth_headers = {"Cookie": "session=fake-test-cookie", "Authorization": "Bearer fake-credential"}
            for upgrade in (False, True):
                Upstream.requests.clear()
                headers = auth_headers | ({"Upgrade": "websocket", "Connection": "Upgrade"} if upgrade else {})
                status, downstream_headers, _ = request(path, headers)
                assert status == (101 if upgrade else 200), status
                assert "Set-Cookie" not in downstream_headers
                auth_request, actual = Upstream.requests
                assert auth_request[1].get("Cookie") == "session=fake-test-cookie"
                assert "Authorization" not in auth_request[1]
                assert "Cookie" not in actual[1] and "Authorization" not in actual[1], actual
        assert request("/upload", method="POST", body=b"x" * (8 * 1024**2))[0] == 200
        assert request("/upload", method="POST", length=8 * 1024**2 + 1)[0] == 413
        print("PASS: nginx syntax; static content/cache/MIME/no Web traffic; retired apps 410; "
              "VNC HTTP/WebSocket auth and header isolation; exact 8 MiB limit")


if __name__ == "__main__":
    check()
