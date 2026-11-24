# Starts LeadFlow CRM locally:
#   1. PostgreSQL + Redis (Docker)
#   2. Database migrations
#   3. API + background workers + CRM screens on http://127.0.0.1:8000
# Usage:  .\start.ps1            (add -Tunnel to also open a public HTTPS tunnel for WhatsApp replies)
param([switch]$Tunnel)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

docker compose -f infra/docker-compose.yml --env-file .env up -d --wait
Push-Location backend
.\.venv\Scripts\alembic.exe upgrade head
Pop-Location

if ($Tunnel) {
    # Free localhost.run tunnel via Windows' built-in ssh. It changes address now and then;
    # app.tunnel notices and re-registers the WhatsApp webhook with Meta automatically.
    Start-Process -FilePath "$PSScriptRoot\backend\.venv\Scripts\python.exe" -ArgumentList "-u","-m","app.tunnel" `
        -WorkingDirectory "$PSScriptRoot\backend" -WindowStyle Minimized
    Write-Host "Tunnel keeper started (minimized window). Current URL: tools\tunnel_url.txt"
}

Write-Host "CRM: http://127.0.0.1:8000"
Push-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Pop-Location
