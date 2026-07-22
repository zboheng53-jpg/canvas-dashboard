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
    assert nginx.count("proxy_set_header X-Forwarded-For $remote_addr;") >= 3


def test_backup_service_and_timer_run_encrypted_backup_cli():
    repo_root = Path(__file__).parents[1]
    service = (repo_root / "deploy" / "canvas-dashboard-backup.service").read_text(encoding="utf-8")
    timer = (repo_root / "deploy" / "canvas-dashboard-backup.timer").read_text(encoding="utf-8")
    runner = (repo_root / "deploy" / "run-backup.sh").read_text(encoding="utf-8")

    assert "run-backup.sh" in service
    assert "scripts/backup_data.py" in runner and "create" in runner
    assert "--public-key /etc/canvas-dashboard/backup-public.pem" in runner
    assert "seq 1 20" in runner
    assert "OnCalendar=daily" in timer
    assert "Persistent=true" in timer


def test_services_run_from_the_atomic_current_release():
    repo_root = Path(__file__).parents[1]
    web = (repo_root / "deploy" / "canvas-dashboard.service").read_text(encoding="utf-8")
    worker = (repo_root / "deploy" / "zhihuishu-worker.service").read_text(encoding="utf-8")
    cleanup = (repo_root / "deploy" / "zhihuishu-login-cleanup.service").read_text(encoding="utf-8")

    for text in (web, worker, cleanup):
        assert "WorkingDirectory=/home/ubuntu/canvas-dashboard/current" in text
    assert "EnvironmentFile=-/etc/canvas-dashboard/canvas-dashboard.env" in web


def test_deploy_archive_uses_only_tracked_release_files():
    repo_root = Path(__file__).parents[1]
    deploy_script = (
        repo_root
        / ".agents"
        / "skills"
        / "deploy-canvas-dashboard"
        / "scripts"
        / "deploy.ps1"
    ).read_text(encoding="utf-8")
    attributes = (repo_root / ".gitattributes").read_text(encoding="utf-8")

    assert "git archive" in deploy_script
    assert "-czf $TarFile *" not in deploy_script
    assert ".agents export-ignore" in attributes


def test_deploy_archive_excludes_non_runtime_files():
    repo_root = Path(__file__).parents[1]
    attributes = (repo_root / ".gitattributes").read_text(encoding="utf-8")

    for entry in (
        "AGENTS.md export-ignore",
        "CLAUDE.md export-ignore",
        "README.md export-ignore",
        "docs export-ignore",
        "tests export-ignore",
        "*.bat export-ignore",
        "*.vbs export-ignore",
        "scripts/*.ps1 export-ignore",
        "deploy/*.md export-ignore",
        "deploy/known_hosts export-ignore",
        "fetch_haoke_raw.py export-ignore",
        "generate_markdown_v4.py export-ignore",
        "tongji-timetable-exporter-v1.2 export-ignore",
        "使用教程.txt export-ignore",
    ):
        assert entry in attributes


def test_release_installer_checks_and_restarts_all_units():
    repo_root = Path(__file__).parents[1]
    install = (repo_root / "deploy" / "install-release.sh").read_text(encoding="utf-8")
    rollback = (repo_root / "deploy" / "rollback-release.sh").read_text(encoding="utf-8")

    assert "nginx -t" in install
    assert "zhihuishu-worker.service" in install
    assert "zhihuishu-login-cleanup.timer" in install
    assert "canvas-dashboard-backup.timer" in install
    assert "curl" in install and "/healthz" in install
    assert "canvas-dashboard.https.nginx" in install
    assert ".previous-release" in install
    assert ".previous-release" in rollback
    assert "canvas-dashboard.https.nginx" in rollback
    assert "seq 1 20" in rollback
    for script in (install, rollback):
        assert "sudo test -f /etc/letsencrypt/live/canvas-dashboard.xyz/fullchain.pem" in script
        assert "--resolve canvas-dashboard.xyz:443:127.0.0.1" in script


def test_release_installer_prunes_old_releases_after_health_checks():
    repo_root = Path(__file__).parents[1]
    install = (repo_root / "deploy" / "install-release.sh").read_text(encoding="utf-8")

    assert "release_retention=5" in install
    assert "prune_old_releases" in install
    assert 'readlink -f "$root/current"' in install
    assert 'cat "$root/.previous-release"' in install
    assert 'rm -rf -- "$candidate"' in install
    assert install.index("systemctl is-active --quiet canvas-dashboard-backup.timer") < install.rindex(
        "prune_old_releases"
    )


def test_calendar_token_paths_are_not_written_to_nginx_access_logs():
    repo_root = Path(__file__).parents[1]
    nginx = (repo_root / "deploy" / "canvas-dashboard.nginx").read_text(encoding="utf-8")

    assert "location ^~ /calendar/" in nginx
    calendar_location = nginx.split("location ^~ /calendar/", 1)[1].split("}", 1)[0]
    assert "access_log off;" in calendar_location


def test_https_template_redirects_http_and_protects_calendar_tokens():
    repo_root = Path(__file__).parents[1]
    https_nginx = (repo_root / "deploy" / "canvas-dashboard.https.nginx").read_text(encoding="utf-8")

    assert "listen 443 ssl" in https_nginx
    assert "server_name canvas-dashboard.xyz www.canvas-dashboard.xyz;" in https_nginx
    assert "return 301 https://$host$request_uri;" in https_nginx
    assert "/etc/letsencrypt/live/canvas-dashboard.xyz/fullchain.pem" in https_nginx
    calendar_location = https_nginx.split("location ^~ /calendar/", 1)[1].split("}", 1)[0]
    assert "access_log off;" in calendar_location


def test_https_enable_script_gates_dns_certificate_and_secure_cookie():
    repo_root = Path(__file__).parents[1]
    script = (repo_root / "deploy" / "enable-https.sh").read_text(encoding="utf-8")

    assert "124.222.188.101" in script
    assert "certbot certonly" in script
    assert "CANVAS_DASHBOARD_COOKIE_SECURE=1" in script
    assert "CANVAS_DASHBOARD_ICP_NUMBER=闽ICP备2026026558号-1" in script
    assert "CANVAS_DASHBOARD_APPLE_CALENDAR_ENABLED=1" in script
    assert "canvas-dashboard.https.nginx" in script
    assert "nginx -t" in script
    assert "--resolve \"$domain:443:127.0.0.1\"" in script
    assert "--resolve \"$domain:80:127.0.0.1\"" in script
