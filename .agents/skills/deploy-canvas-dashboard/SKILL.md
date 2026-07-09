---
name: deploy-canvas-dashboard
description: Deploy changes to the remote production server for the Canvas Dashboard project. Triggers when the user mentions deploying, uploading to server, syncing to production, shipping, restarting service, or putting changes live for canvas-dashboard.
---

# Deploy Canvas Dashboard

Use this skill to deploy the local codebase of Canvas Dashboard to the remote production server.

## Production Server Details
- **IP Address**: `124.222.188.101`
- **Username**: `ubuntu`
- **Deployment Directory**: `/home/ubuntu/canvas-dashboard/`
- **Systemd Service**: `canvas-dashboard.service`

## How to Deploy

Run the deployment script from the project root:

```powershell
.agents\skills\deploy-canvas-dashboard\scripts\deploy.ps1
```

This automated deployment script will:
1. Run local Python unittest suites using `.venv\Scripts\python.exe -m unittest discover -s tests` to prevent shipping broken code.
2. Package the workspace into `canvas-dashboard.tar.gz` excluding files not required on production (`.venv`, `data`, `__pycache__`, `.superpowers`, `.claude`, `.git`, `.pytest_cache`, `.agents`).
3. Copy the packaged archive to the server via `scp`.
4. Extract the archive in `/home/ubuntu/canvas-dashboard/` and clean up the remote copy.
5. Restart the server service with `sudo systemctl restart canvas-dashboard`.
6. Query and output the status of the service using `sudo systemctl status canvas-dashboard` to verify deployment was successful.
