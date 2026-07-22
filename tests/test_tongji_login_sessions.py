import json

import tongji_login_sessions as sessions


def test_tongji_session_uses_separate_ports_and_local_debugger(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions, "DATA_DIR", tmp_path)

    command = sessions.build_docker_command("alice", "tok_123456789012", 6207, 6307)

    assert "canvas-dashboard=tongji-login" in command
    assert "127.0.0.1:6207:6080" in command
    assert "127.0.0.1:6307:9223" in command
    assert "LOGIN_URL=https://1.tongji.edu.cn/GraduateStudentTimeTable" in command
    assert "CHROME_REMOTE_DEBUGGING_PORT=9222" in command
    assert "CHROME_REMOTE_DEBUGGING_PROXY_PORT=9223" in command
    assert (tmp_path / "users" / "alice" / "tongji_login_profile").is_dir()


def test_tongji_session_cleanup_stops_container_and_removes_ephemeral_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions, "DATA_DIR", tmp_path)
    profile = tmp_path / "users" / "alice" / "tongji_login_profile"
    profile.mkdir(parents=True)
    (profile / "cookie").write_text("temporary", encoding="utf-8")
    session_file = tmp_path / "users" / "alice" / "tongji_login_session.json"
    session_file.write_text(json.dumps({
        "username": "alice", "token": "tok_123456789012", "container_name": "container", "expires_at": 0,
    }), encoding="utf-8")
    stopped = []
    monkeypatch.setattr(sessions, "_stop_container", stopped.append)

    assert sessions.cleanup_expired_sessions(now=1) == 1
    assert stopped == ["container"]
    assert not session_file.exists()
    assert not profile.exists()
