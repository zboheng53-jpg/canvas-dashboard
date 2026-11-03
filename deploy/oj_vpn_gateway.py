"""Restricted CONNECT gateway inside the OJ VPN network namespace."""
import select
import socket
import socketserver
import threading

ALLOWED = frozenset({"oj.tongji.edu.cn", "iam.tongji.edu.cn"})
MAX_HEADER = 16384
MAX_CONNECTIONS = 64


class Gateway(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address):
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(10)
        try:
            first = self.rfile.readline(MAX_HEADER + 1)
            parts = first.decode("ascii").strip().split()
            if len(parts) != 3 or parts[0] != "CONNECT" or parts[2] not in ("HTTP/1.0", "HTTP/1.1"):
                return self.reject(400)
            authority = parts[1].lower()
            if authority not in {host + ":443" for host in ALLOWED}:
                return self.reject(403)
            remaining = MAX_HEADER - len(first)
            while remaining > 0:
                line = self.rfile.readline(remaining + 1)
                remaining -= len(line)
                if line in (b"\r\n", b"\n"):
                    break
                if not line or remaining <= 0:
                    return self.reject(400)
            else:
                return self.reject(400)
            host = authority[:-4]
            with socket.create_connection((host, 443), timeout=10) as upstream:
                self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                self.wfile.flush()
                self.connection.settimeout(None)
                upstream.settimeout(None)
                peers = {self.connection: upstream, upstream: self.connection}
                while True:
                    ready, _, _ = select.select(list(peers), [], [], 90)
                    if not ready:
                        return
                    for src in ready:
                        data = src.recv(65536)
                        if not data:
                            return
                        peers[src].sendall(data)
        except (OSError, UnicodeError, ValueError):
            return

    def reject(self, status):
        self.wfile.write(f"HTTP/1.1 {status} Error\r\nConnection: close\r\n\r\n".encode("ascii"))


if __name__ == "__main__":
    with Gateway(("0.0.0.0", 18080)) as server:
        server.serve_forever()
