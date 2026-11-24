# Build the LeadNest app image on this PC and copy it to the server.
# Use this for small servers (e.g. Oracle E2.1.Micro, 1 GB RAM) where building on the server is too heavy.
# The PC and the server must have the same CPU type (x86/amd64 for E2.1.Micro).
#
# Run from the leadflow-crm folder:
#   powershell -ExecutionPolicy Bypass -File deploy\ship-image.ps1 -Server 1.2.3.4 -Key C:\path\to\ssh-key.key
param(
    [Parameter(Mandatory = $true)][string]$Server,
    [Parameter(Mandatory = $true)][string]$Key,
    [string]$User = "ubuntu"
)
$ErrorActionPreference = "Stop"
$tar = Join-Path $env:TEMP "leadnest-app.tar"

Write-Host "==> Building image leadnest-app:latest (linux/amd64)"
docker build --platform linux/amd64 -t leadnest-app:latest .
if ($LASTEXITCODE -ne 0) { throw "docker build failed" }

Write-Host "==> Saving image to $tar"
docker save leadnest-app:latest -o $tar
if ($LASTEXITCODE -ne 0) { throw "docker save failed" }

Write-Host "==> Uploading to $User@$Server (this can take a few minutes)"
scp -i $Key $tar "${User}@${Server}:leadnest-app.tar"
if ($LASTEXITCODE -ne 0) { throw "upload failed" }

Write-Host "==> Loading image on the server"
ssh -i $Key "$User@$Server" "docker load -i ~/leadnest-app.tar && rm ~/leadnest-app.tar"
if ($LASTEXITCODE -ne 0) { throw "docker load failed" }

Remove-Item $tar
Write-Host "==> Done. On the server run:  lnc up -d   (without --build)"
