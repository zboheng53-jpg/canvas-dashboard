"""Keep the OJ-only VPN gateway available inside its isolated container."""
import json
import os
import pty
import re
import select
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from oj_vpn_gateway import Gateway

CLIENT = "/opt/MotionPro/vpn_cmdline"
DNS = "nameserver 202.120.190.208\nnameserver 202.120.190.108\n"
PORT_FILE = "/var/log/MotionPro/com.arraynetworks.vpn.port"


def _vpnd_pids():
    pids = []
    if not os.path.exists("/proc"):
        return pids
    try:
        for entry in os.listdir("/proc"):
            if entry.isdigit():
                try:
                    with open(f"/proc/{entry}/cmdline", "rb") as f:
                        cmd = f.read()
                    if b"/usr/bin/vpnd" in cmd or cmd.startswith(b"vpnd\0"):
                        pids.append(int(entry))
                except OSError:
                    pass
    except OSError:
        pass
    return pids


def _check_daemon_port():
    try:
        with open(PORT_FILE, "r") as f:
            port = int(f.read().strip())
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except (OSError, ValueError):
        return False


def ensure_daemon():
    """Ensure EXACTLY ONE vpnd is running and ready for IPC before starting vpn_cmdline."""
    if not os.path.exists("/usr/bin/vpnd"):
        return True
    pids = _vpnd_pids()
    if len(pids) != 1:
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        time.sleep(0.5)
        try:
            subprocess.Popen(["/usr/bin/vpnd"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if _check_daemon_port() and len(_vpnd_pids()) == 1:
            return True
        time.sleep(0.2)
    return False


def disconnect():
    try:
        subprocess.run([CLIENT, "-s"], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass


def connect(credentials):
    """Answer the client's interactive prompts without putting secrets in argv or logs."""
    ensure_daemon()
    master, slave = pty.openpty()
    process = subprocess.Popen(
        [CLIENT, "-h", "vpn.tongji.cn", "-m", "LDAP", "-l", "info"],
        stdin=slave, stdout=slave, stderr=slave, close_fds=True,
    )
    os.close(slave)
    output = b""
    method_sent = username_sent = password_sent = False
    deadline = time.monotonic() + 60
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 0.5)
            if ready:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    chunk = b""
                if not chunk and process.poll() is not None:
                    break
                output = (output + chunk)[-16384:]
                lower = output.lower()
                if not method_sent and b"choose login method number" in lower:
                    match = re.search(rb"(?m)^\s*(\d+)\s+LDAP\s*$", output)
                    if not match:
                        return False, True
                    os.write(master, match.group(1) + b"\n")
                    method_sent = True
                    print("VPN authentication method selected", flush=True)
                if not username_sent and b"input username:" in lower:
                    os.write(master, (credentials["username"] + "\n").encode())
                    username_sent = True
                    print("VPN account submitted", flush=True)
                if not password_sent and b"input password:" in lower:
                    os.write(master, (credentials["password"] + "\n").encode())
                    password_sent = True
                    print("VPN authentication submitted", flush=True)
                if b"login failed" in lower or "登录失败".encode() in output:
                    return False, True
                if b"vpn is connected" in lower:
                    return True, False
            if process.poll() is not None and not ready:
                break
        lower = output.lower()
        states = re.findall(rb"current status:\s*(-?\d+)", lower)
        clean = output
        if credentials.get("password"):
            clean = clean.replace(credentials["password"].encode(), b"***")
        print("VPN login did not finish: "
              f"method={method_sent} account={username_sent} password={password_sent} "
              f"authenticated={b'login successfully' in lower} "
              f"tunnel_started={b'starting vpn' in lower} "
              f"other_session={b'another computer' in lower or b'already logged' in lower} "
              f"socket_error={b'connect to the socket' in lower or b'connect to ssl' in lower} "
              f"status_codes={[int(value) for value in states[-5:]]} "
              f"exit={process.poll()}\n"
              f"Raw output (sanitized):\n{clean.decode('utf-8', errors='replace')}", flush=True)
        return False, False
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        os.close(master)


def healthy():
    try:
        status = subprocess.run([CLIENT, "-a"], capture_output=True, text=True, timeout=10)
        if status.returncode != 0 or "VPN Status: connected" not in status.stdout:
            return False
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("https://oj.tongji.edu.cn/", timeout=12) as response:
            return response.status == 200
    except (OSError, subprocess.SubprocessError, urllib.error.URLError):
        return False


def _handle_term(signum, frame):
    disconnect()
    sys.exit(0)


try:
    signal.signal(signal.SIGTERM, _handle_term)
    signal.signal(signal.SIGINT, _handle_term)
except (ValueError, OSError):
    pass


def main():
    try:
        credentials = json.load(sys.stdin)
        if not all(isinstance(credentials.get(k), str) and credentials[k] for k in ("username", "password")):
            raise ValueError("invalid credentials")
    except (OSError, ValueError, TypeError):
        print("VPN credentials unavailable", flush=True)
        return 77

    connected, rejected = connect(credentials)
    if not connected and not rejected:
        print("VPN connection failed on first attempt, disconnecting and retrying...", flush=True)
        disconnect()
        time.sleep(3)
        connected, rejected = connect(credentials)
    credentials.clear()
    if not connected:
        disconnect()
        print("VPN login rejected" if rejected else "VPN connection failed", flush=True)
        return 77 if rejected else 1
    with open("/etc/resolv.conf", "w", encoding="ascii") as resolver:
        resolver.write(DNS)
    if not healthy():
        print("VPN OJ health check failed", flush=True)
        disconnect()
        return 1
    gateway = Gateway(("0.0.0.0", 18080))
    threading.Thread(target=gateway.serve_forever, daemon=True).start()
    print("OJ VPN gateway ready", flush=True)
    failures = 0
    while True:
        time.sleep(30)
        failures = 0 if healthy() else failures + 1
        if failures >= 3:
            gateway.shutdown()
            gateway.server_close()
            print("VPN OJ health check lost", flush=True)
            disconnect()
            return 1


if __name__ == "__main__":
    sys.exit(main())
