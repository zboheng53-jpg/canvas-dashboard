# Canvas Dashboard

Flask web app for a personal Tongji University homework dashboard. It collects unfinished tasks from Canvas, Haoke, Zhixuemeng, Zhihuishu, and manual todos.

## Run Locally

```powershell
pip install -r requirements.txt
python app.py
```

Production entry point:

```powershell
python serve.py
```

The app listens on port `5000` by default.

## Data Safety

`data/` is runtime-only and must never be committed.

It may contain:

- `data/.encryption_key`
- `data/.flask_secret_key`
- account registry and per-user credentials
- cookies, browser profiles, caches, and logs

Keep real runtime data on the machine or production server only. Use `.env.example` as the public template for local-only settings.

## Tests

```powershell
python -m pytest
```

Use the project virtual environment when available:

```powershell
.venv\Scripts\python.exe -m pytest
```

