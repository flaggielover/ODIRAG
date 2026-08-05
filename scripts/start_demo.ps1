[CmdletBinding()]
param(
    [switch]$SkipSeed
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required but was not found on PATH."
}

& docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose v2 is required."
}

$demoPasswordInjected = $false
$envFile = Join-Path $repositoryRoot ".env"
$envDefinesAdminPassword = $false
if (Test-Path $envFile) {
    $envDefinesAdminPassword = [bool](Select-String -LiteralPath $envFile -Pattern '^\s*ODIRAG_ADMIN_PASSWORD=' -Quiet)
}
if (-not (Test-Path Env:ODIRAG_ADMIN_PASSWORD) -and -not $envDefinesAdminPassword) {
    $env:ODIRAG_ADMIN_PASSWORD = "development-only-admin-password"
    $demoPasswordInjected = $true
}

$demoOverrides = [ordered]@{
    ODIRAG_EMBEDDING_PROVIDER = "deterministic"
    ODIRAG_EMBEDDING_CACHE_PROVIDER = "redis"
    ODIRAG_EMBEDDING_DIMENSIONS = "64"
    ODIRAG_EMBEDDING_VERSION = "demo-v1"
    ODIRAG_VECTOR_STORE_PROVIDER = "qdrant"
    ODIRAG_QDRANT_COLLECTION = "odirag_demo_chunks_v1"
    ODIRAG_RERANK_PROVIDER = "deterministic"
}
$previousDemoEnvironment = @{}
foreach ($name in $demoOverrides.Keys) {
    $exists = Test-Path "Env:$name"
    $previousDemoEnvironment[$name] = @{
        Exists = $exists
        Value = if ($exists) { (Get-Item "Env:$name").Value } else { $null }
    }
    Set-Item -Path "Env:$name" -Value $demoOverrides[$name]
}

Push-Location $repositoryRoot
try {
    & docker compose build backend
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed to build the backend image."
    }
    & docker compose build frontend
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed to build the frontend image."
    }
    & docker compose --profile ui --profile async up --detach --no-build
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed to start the ODIRAG stack."
    }

    $ready = $false
    for ($attempt = 1; $attempt -le 90; $attempt++) {
        $containerId = & docker compose ps --quiet backend | Select-Object -First 1
        if ($LASTEXITCODE -eq 0 -and $containerId) {
            $state = & docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $containerId
            if ($LASTEXITCODE -eq 0 -and $state.Trim() -eq "healthy") {
                $ready = $true
                break
            }
        }
        Start-Sleep -Seconds 2
    }

    if (-not $ready) {
        & docker compose logs backend
        throw "The backend did not become healthy within 180 seconds."
    }

    if (-not $SkipSeed) {
        & docker compose exec -T backend /app/deployment/initialize-demo.sh
        if ($LASTEXITCODE -ne 0) {
            throw "The stack started, but demo data seeding or reindexing failed."
        }
    }

    $uiAddress = & docker compose port nginx 80 | Select-Object -First 1
    $apiAddress = & docker compose port backend 8000 | Select-Object -First 1
    Write-Host "ODIRAG is ready."
    Write-Host "UI:  http://$uiAddress"
    Write-Host "API: http://$apiAddress/api/docs"
    Write-Host "Retrieval: deterministic embeddings + Qdrant + deterministic reranking"
    Write-Host "Login: ODIRAG_ADMIN_USERNAME / ODIRAG_ADMIN_PASSWORD (defaults: admin / development-only-admin-password)"
}
finally {
    Pop-Location
    foreach ($name in $demoOverrides.Keys) {
        $previous = $previousDemoEnvironment[$name]
        if ($previous.Exists) {
            Set-Item -Path "Env:$name" -Value $previous.Value
        }
        else {
            Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
        }
    }
    if ($demoPasswordInjected) {
        Remove-Item Env:ODIRAG_ADMIN_PASSWORD
    }
}
