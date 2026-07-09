from pathlib import Path

import pytest


def test_create_session_records_token_and_user(tmp_path, monkeypatch):
    import zhihuishu_login_sessions as sessions

    monkeypatch.setattr(sessions, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sessions, "_run_docker", lambda command: None)
    monkeypatch.setattr(sessions, "_wait_for_novnc", lambda port: None, raising=False)
    monkeypatch.setattr(sessions, "_find_free_port", lambda: 6107)

    session = sessions.create_session("alice", now=1000.0)

    assert session["username"] == "alice"
    assert session["port"] == 6107
    assert session["expires_at"] == 1600.0
    assert session["url"] == f"/zhihuishu/session/{session['token']}/"
    assert sessions.validate_session(session["token"], 6107, now=1001.0)


def test_validate_rejects_expired_or_wrong_port(tmp_path, monkeypatch):
    import zhihuishu_login_sessions as sessions

    removed = []
    monkeypatch.setattr(sessions, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sessions, "_run_docker", lambda command: None)
    monkeypatch.setattr(sessions, "_wait_for_novnc", lambda port: None, raising=False)
    monkeypatch.setattr(sessions, "_find_free_port", lambda: 6107)
    monkeypatch.setattr(sessions, "_stop_container", lambda name: removed.append(name))

    session = sessions.create_session("alice", now=1000.0)

    assert not sessions.validate_session(session["token"], 6108, now=1001.0)
    assert not sessions.validate_session(session["token"], 6107, now=1601.0)
    assert sessions.load_session("alice") is None
    assert removed == [session["container_name"]]


def test_validate_rejects_bad_token_format_and_out_of_range_port(tmp_path, monkeypatch):
    import zhihuishu_login_sessions as sessions

    monkeypatch.setattr(sessions, "DATA_DIR", tmp_path)
    sessions._save_session("alice", {
        "username": "alice",
        "token": "../bad",
        "port": 6107,
        "container_name": "canvas-zhs-login-bad",
        "expires_at": 1600.0,
    })
    sessions._save_session("bob", {
        "username": "bob",
        "token": "valid_token_1234567890",
        "port": 6200,
        "container_name": "canvas-zhs-login-port",
        "expires_at": 1600.0,
    })

    assert not sessions.validate_session("../bad", 6107, now=1001.0)
    assert not sessions.validate_session("valid_token_1234567890", 6200, now=1001.0)


def test_nginx_vnc_proxy_limits_port_and_token_pattern():
    nginx = (Path(__file__).parents[1] / "deploy" / "canvas-dashboard.nginx").read_text(encoding="utf-8")

    assert "(?<zhs_port>61[0-9]{2})" in nginx
    assert "(?<zhs_token>[A-Za-z0-9_-]{16,128})" in nginx
    assert "@zhs_vnc_denied" in nginx


def test_build_docker_command_mounts_only_user_profile(tmp_path, monkeypatch):
    import zhihuishu_login_sessions as sessions

    monkeypatch.setattr(sessions, "DATA_DIR", tmp_path)

    command = sessions.build_docker_command("alice", "tok123", 6107)
    joined = " ".join(command)

    assert command[:3] == ["docker", "run", "-d"]
    assert "--rm" in command
    assert "127.0.0.1:6107:6080" in joined
    assert "zhihuishu_chromium_profile:/profile" in joined
    assert "users/alice/zhihuishu_chromium_profile" in joined.replace("\\", "/")
    assert "data:" not in joined.replace("\\", "/")


def test_stop_session_removes_metadata_and_container(tmp_path, monkeypatch):
    import zhihuishu_login_sessions as sessions

    removed = []
    monkeypatch.setattr(sessions, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sessions, "_run_docker", lambda command: None)
    monkeypatch.setattr(sessions, "_wait_for_novnc", lambda port: None, raising=False)
    monkeypatch.setattr(sessions, "_find_free_port", lambda: 6107)
    monkeypatch.setattr(sessions, "_stop_container", lambda name: removed.append(name))

    session = sessions.create_session("alice", now=1000.0)
    assert sessions.stop_session("alice", session["token"])

    assert removed == [session["container_name"]]
    assert sessions.load_session("alice") is None


def test_create_session_waits_for_novnc_before_returning(tmp_path, monkeypatch):
    import zhihuishu_login_sessions as sessions

    events = []
    monkeypatch.setattr(sessions, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sessions, "_run_docker", lambda command: events.append("docker"))
    monkeypatch.setattr(sessions, "_wait_for_novnc", lambda port: events.append(("ready", port)), raising=False)
    monkeypatch.setattr(sessions, "_find_free_port", lambda: 6107)

    sessions.create_session("alice", now=1000.0)

    assert events == ["docker", ("ready", 6107)]


def test_create_session_stops_container_when_novnc_is_not_ready(tmp_path, monkeypatch):
    import zhihuishu_login_sessions as sessions

    removed = []

    def not_ready(port):
        raise RuntimeError("noVNC not ready")

    monkeypatch.setattr(sessions, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sessions.secrets, "token_urlsafe", lambda length: "tok")
    monkeypatch.setattr(sessions, "_run_docker", lambda command: None)
    monkeypatch.setattr(sessions, "_wait_for_novnc", not_ready, raising=False)
    monkeypatch.setattr(sessions, "_find_free_port", lambda: 6107)
    monkeypatch.setattr(sessions, "_stop_container", lambda name: removed.append(name))

    with pytest.raises(RuntimeError, match="noVNC not ready"):
        sessions.create_session("alice", now=1000.0)

    assert removed == ["canvas-zhs-login-tok"]
    assert sessions.load_session("alice") is None


def test_run_docker_reports_missing_runtime_clearly(monkeypatch):
    import zhihuishu_login_sessions as sessions

    def missing_docker(command, check=True):
        raise FileNotFoundError(2, "The system cannot find the file specified", "docker")

    monkeypatch.setattr(sessions.subprocess, "run", missing_docker)

    with pytest.raises(RuntimeError) as excinfo:
        sessions._run_docker(["docker", "run"])

    message = str(excinfo.value)
    assert "Docker" in message
    assert "智慧树登录窗口" in message


def test_stop_session_clears_metadata_when_docker_is_missing(tmp_path, monkeypatch):
    import zhihuishu_login_sessions as sessions

    def missing_docker(command, check=False):
        raise FileNotFoundError(2, "The system cannot find the file specified", "docker")

    monkeypatch.setattr(sessions, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sessions.subprocess, "run", missing_docker)
    sessions._save_session("alice", {
        "username": "alice",
        "token": "tok",
        "container_name": "canvas-zhs-login-tok",
    })

    assert sessions.stop_session("alice", "tok")
    assert sessions.load_session("alice") is None
