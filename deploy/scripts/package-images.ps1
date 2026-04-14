param(
    [string]$ArchiveName = "kie-agent-images.tar"
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")

Write-Host "[INFO] Building Docker images..." -ForegroundColor Cyan
docker compose build

Write-Host "[INFO] Saving images to $ArchiveName ..." -ForegroundColor Cyan
docker save -o $ArchiveName `
  kie-agent-backend:latest `
  kie-agent-worker:latest `
  kie-agent-frontend:latest

Write-Host "[OK] Offline package created: $ArchiveName" -ForegroundColor Green
