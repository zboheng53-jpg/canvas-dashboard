"""Local correctness under 20 clients and blocked upstream; no production capacity claim."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import statistics
import threading
import time

import pytest
import requests

import app
import auth
import canvas_auth
import http_sync
from storage import read_json_file, write_json_file


@pytest.mark.waitress(threads=8)
def test_twenty_clients_can_edit_local_tasks_while_two_upstream_jobs_are_blocked(live_app, isolated_data, monkeypatch):
    sessions = []
    signer = app.app.session_interface.get_signing_serializer(app.app)
    for index in range(20):
        username = f'loaduser{index}'
        assert auth.register(username, 'password1')[0]
        identity = auth.session_identity(username)
        write_json_file(isolated_data / 'users' / username / 'config.json', {'calendar_feed_url': 'https://canvas.tongji.edu.cn/feed.ics'})
        client = requests.Session()
        client.cookies.set(app.app.config['SESSION_COOKIE_NAME'], signer.dumps({'username': username, 'account_id': identity[0], 'session_version': identity[1], '_csrf_token': 'load-test'}))
        sessions.append((username, client))
    monkeypatch.setattr(canvas_auth, 'validate_feed_url', lambda _: (True, None))
    # This workload exercises the real cold-cache route, rather than the
    # standard live_app fixture's pre-seeded Canvas projection.
    monkeypatch.setattr(app, 'get_canvas_cached_todos', canvas_auth.get_cached_todos)
    released = threading.Event()
    condition = threading.Condition()
    calls = []
    class Response:
        status_code = 200
        text = 'calendar'
    def blocked_get(*args, **kwargs):
        with condition:
            calls.append(True)
            condition.notify_all()
        assert released.wait(15)
        return Response()
    monkeypatch.setattr(canvas_auth.requests, 'get', blocked_get)
    monkeypatch.setattr(canvas_auth, '_parse_ical', lambda _: [])
    durations = []
    def client_work(entry):
        username, client = entry
        start = time.perf_counter()
        result = client.get(live_app + '/api/canvas/todos', timeout=5)
        assert result.status_code == 200 and result.json()['data'] == []
        created = client.post(live_app + '/api/custom/todos', headers={'X-CSRF-Token': 'load-test'}, json={'text': username + ' local task'}, timeout=5)
        assert created.status_code == 200
        todo = created.json()['todo']
        updated = client.put(live_app + f'/api/custom/todos/{todo["id"]}', headers={'X-CSRF-Token': 'load-test'}, json={'done': True, 'expected_updated_at': todo['updated_at']}, timeout=5)
        assert updated.status_code == 200
        durations.append(time.perf_counter() - start)
    try:
        with ThreadPoolExecutor(20) as pool:
            list(pool.map(client_work, sessions))
        with condition:
            assert condition.wait_for(lambda: len(calls) == 2, timeout=5)
        assert len(calls) == 2  # Remaining requests are queued, not extra threads.
        for username, _ in sessions:
            todos = read_json_file(isolated_data / 'users' / username / 'custom_todos.json', [])
            assert len(todos) == 1 and todos[0]['text'] == username + ' local task' and todos[0]['done']
    finally:
        released.set()
        http_sync._executor.submit(lambda: None).result(timeout=10)
        http_sync._executor.submit(lambda: None).result(timeout=10)
    artifact = os.environ.get('CANVAS_TEST_ARTIFACTS')
    if artifact:
        ordered = sorted(durations)
        (Path(artifact) / 'mixed-load.json').write_text(json.dumps({'environment': 'local Windows, Waitress 8 threads, fake upstream', 'clients': 20, 'http_workers': 2, 'completed_local_edit_sequences': len(durations), 'sequence_p50_seconds': statistics.median(ordered), 'sequence_p95_seconds': ordered[18], 'sequence_max_seconds': max(ordered)}, indent=2), encoding='utf-8')
