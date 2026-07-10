from pathlib import Path


def test_zhihuishu_login_cleanup_timer_uses_cleanup_cli():
    repo_root = Path(__file__).parents[1]
    service = repo_root / "deploy" / "zhihuishu-login-cleanup.service"
    timer = repo_root / "deploy" / "zhihuishu-login-cleanup.timer"

    service_text = service.read_text(encoding="utf-8")
    timer_text = timer.read_text(encoding="utf-8")

    assert "WorkingDirectory=/home/ubuntu/canvas-dashboard" in service_text
    assert ".venv/bin/python zhihuishu_login_sessions.py --cleanup-expired" in service_text
    assert "OnBootSec=" in timer_text
    assert "OnUnitActiveSec=" in timer_text


def test_nginx_overwrites_forwarded_for_with_the_connecting_client_ip():
    repo_root = Path(__file__).parents[1]
    nginx = (repo_root / "deploy" / "canvas-dashboard.nginx").read_text(encoding="utf-8")

    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" not in nginx
    assert nginx.count("proxy_set_header X-Forwarded-For $remote_addr;") == 2
