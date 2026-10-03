# Despliega RutaUD en el servidor: compila Angular en este PC (el e2-micro de 1 GB no
# alcanza a compilarlo), sube dist/web y reconstruye los contenedores.
# Uso: .\scripts\deploy.ps1   (sube primero tus cambios a GitHub: el servidor hace git pull)
param(
    [string]$Server = "ubuntu@35.207.24.145",
    [string]$Key = "$HOME\.ssh\rutaud"
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$bundle = Join-Path $env:TEMP "rutaud-web-dist.tgz"

Push-Location (Join-Path $root "apps\web")
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Falló el build de Angular" }
} finally {
    Pop-Location
}

tar -czf $bundle -C (Join-Path $root "apps\web") dist/web
scp -i $Key $bundle "${Server}:/tmp/rutaud-web-dist.tgz"
ssh -i $Key $Server "set -e; cd PortalEmpleoUD; git pull --ff-only; rm -rf apps/web/dist; tar -xzf /tmp/rutaud-web-dist.tgz -C apps/web; sudo docker compose -f docker-compose.yml -f docker-compose.prebuilt.yml up -d --build; sudo docker image prune -f"
