param(
    [string]$BaseUrl = "http://127.0.0.1:8080",
    [string]$Query = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$composeEnv = Join-Path $repositoryRoot ".env"

function Read-DotEnvValue {
    param([string]$Path, [string]$Name)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    $prefix = "$Name="
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
            $value = $line.Substring($prefix.Length).Trim()
            if (
                $value.Length -ge 2 -and
                (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                 ($value.StartsWith("'") -and $value.EndsWith("'")))
            ) {
                return $value.Substring(1, $value.Length - 2)
            }
            return $value
        }
    }
    return $null
}

$username = $env:ODIRAG_ADMIN_USERNAME
if ([string]::IsNullOrWhiteSpace($username)) {
    $username = Read-DotEnvValue -Path $composeEnv -Name "ODIRAG_ADMIN_USERNAME"
}
if ([string]::IsNullOrWhiteSpace($username)) {
    $username = "admin"
}

$password = $env:ODIRAG_ADMIN_PASSWORD
if ([string]::IsNullOrWhiteSpace($password)) {
    $password = Read-DotEnvValue -Path $composeEnv -Name "ODIRAG_ADMIN_PASSWORD"
}
if ([string]::IsNullOrWhiteSpace($password)) {
    throw "ODIRAG_ADMIN_PASSWORD is required for live Playwright acceptance."
}

$env:E2E_LIVE = "1"
$env:E2E_BASE_URL = $BaseUrl
$env:E2E_USERNAME = $username
$env:E2E_PASSWORD = $password
if (-not [string]::IsNullOrWhiteSpace($Query)) {
    $env:E2E_QUERY = $Query
}
else {
    Remove-Item Env:E2E_QUERY -ErrorAction SilentlyContinue
}

Push-Location (Join-Path $repositoryRoot "frontend")
try {
    npm run test:e2e -- e2e/live-stack.spec.ts
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
    Remove-Item Env:E2E_PASSWORD -ErrorAction SilentlyContinue
}
