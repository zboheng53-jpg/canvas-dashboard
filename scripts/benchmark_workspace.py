"""Local, synthetic Waitress capacity probe; never connects to production/platforms.

Run with the project's Python. Results describe this machine and the seeded read
workload, not a production user limit. All account data is temporary.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clients', default='1,5,10,20')
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    clients = [int(value) for value in args.clients.split(',')]
    if not clients or min(clients) < 1 or max(clients) > 50 or not 1 <= args.rounds <= 20:
        parser.error('Use 1–50 clients and 1–20 rounds')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory(prefix='canvas-capacity-') as temp:
        os.environ['CANVAS_DASHBOARD_DATA_DIR'] = temp
        import requests
        from waitress.server import create_server
        from app import app
        import auth
        import project_store
        from storage import write_json_file
        from user_paths import user_dir
        from services import academic

        academic._get_holidays = lambda: []
        app.config.update(TESTING=False, SESSION_COOKIE_SECURE=False)
        today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        cookies = []
        for i in range(max(clients)):
            username = f'bench{i:03}'
            auth.register(username, 'synthetic-local-only-password')
            project = project_store.create_project(username, {'name': 'Synthetic project'})
            for n in range(5):
                project_store.create_task(username, project['id'], {'name': f'Action {n}', 'planned_on': today})
            write_json_file(user_dir(username) / 'custom_todos.json', [
                {'id': n + 1, 'text': f'Synthetic todo {n}', 'done': False, 'due_date': today,
                 'created_at': today, 'updated_at': today, 'subtasks': []} for n in range(30)
            ])
            account_id, version = auth.session_identity(username)
            cookies.append(app.session_interface.get_signing_serializer(app).dumps(
                {'username': username, 'account_id': account_id, 'session_version': version}))
        server = create_server(app, host='127.0.0.1', port=0, threads=8, map={})
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.effective_port}'
        paths = ['/api/custom/todos', '/api/projects', '/api/actions', f'/api/agenda?start={today}&end={today}']
        report = {'scope': 'local synthetic reads; excludes real sync, browser login, TLS and production hardware',
                  'threads': 8, 'todos_per_user': 30, 'project_actions_per_user': 5, 'rounds': args.rounds, 'runs': []}
        try:
            for count in clients:
                barrier = threading.Barrier(count)
                def run(index):
                    samples, failures = [], 0
                    with requests.Session() as session:
                        session.trust_env = False
                        session.cookies.set('session', cookies[index])
                        barrier.wait(timeout=30)
                        for _ in range(args.rounds):
                            for path in paths:
                                start = time.perf_counter()
                                response = session.get(base + path, timeout=30)
                                samples.append((time.perf_counter()-start)*1000)
                                failures += int(response.status_code != 200 or not response.json().get('ok'))
                    return samples, failures
                start = time.perf_counter()
                with ThreadPoolExecutor(count) as pool:
                    results = list(pool.map(run, range(count)))
                elapsed = time.perf_counter()-start
                samples = sorted(t for values, _ in results for t in values)
                report['runs'].append({'concurrent_clients': count, 'requests': len(samples),
                    'failures': sum(f for _, f in results), 'p50_ms': round(statistics.median(samples), 1),
                    'p95_ms': round(samples[min(len(samples)-1, int(len(samples)*0.95))], 1),
                    'requests_per_second': round(len(samples)/elapsed, 1)})
        finally:
            server.task_dispatcher.shutdown()
            server.close()
            thread.join(timeout=5)
        output = json.dumps(report, ensure_ascii=False, indent=2)
        print(output)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding='utf-8')
        return 1 if any(r['failures'] for r in report['runs']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
