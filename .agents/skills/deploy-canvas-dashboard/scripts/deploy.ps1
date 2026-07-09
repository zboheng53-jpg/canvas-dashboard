# deploy.ps1
# Deploy script for Canvas Dashboard
# Usage: .\deploy.ps1

Write-Host "Starting deployment of Canvas Dashboard..." -ForegroundColor Cyan

# 1. Run local tests & verify syntax
Write-Host "Running local tests and compiling files..." -ForegroundColor Yellow
& .venv\Scripts\python.exe -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) {
    Write-Error "Local tests failed. Deployment aborted."
    exit 1
}

# 2. Package files
Write-Host "Creating archive (excluding .venv, data, cache, etc.)..." -ForegroundColor Yellow
$tarFile = "canvas-dashboard.tar.gz"
if (Test-Path $tarFile) { Remove-Item $tarFile }

# Execute tar
tar --exclude='.venv' --exclude='data' --exclude='__pycache__' --exclude='.superpowers' --exclude='.claude' --exclude='.git' --exclude='.pytest_cache' --exclude='.agents' --exclude='canvas-dashboard.tar.gz' -czf $tarFile *
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to create archive. Deployment aborted."
    exit 1
}

# 3. Upload archive
Write-Host "Uploading archive to production server..." -ForegroundColor Yellow
scp -o StrictHostKeyChecking=no $tarFile ubuntu@124.222.188.101:/home/ubuntu/canvas-dashboard/
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to upload archive via SCP. Deployment aborted."
    Remove-Item $tarFile -ErrorAction SilentlyContinue
    exit 1
}

# 4. Extract on remote server
Write-Host "Extracting archive on remote server..." -ForegroundColor Yellow
ssh -o StrictHostKeyChecking=no ubuntu@124.222.188.101 "tar -xzf /home/ubuntu/canvas-dashboard/$tarFile -C /home/ubuntu/canvas-dashboard/ && rm /home/ubuntu/canvas-dashboard/$tarFile"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to extract archive on remote server. Deployment aborted."
    Remove-Item $tarFile -ErrorAction SilentlyContinue
    exit 1
}

# 5. Restart systemd service
Write-Host "Restarting systemd service on remote server..." -ForegroundColor Yellow
ssh -o StrictHostKeyChecking=no ubuntu@124.222.188.101 "sudo systemctl restart canvas-dashboard"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to restart canvas-dashboard service."
    Remove-Item $tarFile -ErrorAction SilentlyContinue
    exit 1
}

# 6. Verify service status
Write-Host "Checking service status..." -ForegroundColor Yellow
ssh -o StrictHostKeyChecking=no ubuntu@124.222.188.101 "sudo systemctl status canvas-dashboard"

# Cleanup
Remove-Item $tarFile -ErrorAction SilentlyContinue
Write-Host "Deployment completed successfully!" -ForegroundColor Green
