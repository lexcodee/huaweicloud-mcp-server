# Wrapper that loads .env then runs the MCP server.
# Lets ~/.hermes/config.yaml stay free of credentials.
#
# Usage:
#   powershell -File scripts/run-with-env.ps1
#   # or with a custom env file:
#   $env:HWC_MCP_ENV_FILE = "C:\path\to\.env"; powershell -File scripts/run-with-env.ps1

$ErrorActionPreference = "Stop"

$EnvFile = if ($env:HWC_MCP_ENV_FILE) { $env:HWC_MCP_ENV_FILE } else { Join-Path $PSScriptRoot ".." ".env" }
$EnvFile = [System.IO.Path]::GetFullPath($EnvFile)

if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line -split "=", 2
            if ($parts.Length -eq 2) {
                $key = $parts[0].Trim()
                $val = $parts[1].Trim()
                # Strip surrounding quotes
                if ($val.StartsWith('"') -and $val.EndsWith('"')) { $val = $val.Substring(1, $val.Length - 2) }
                if ($val.StartsWith("'") -and $val.EndsWith("'")) { $val = $val.Substring(1, $val.Length - 2) }
                Set-Item -Path "env:$key" -Value $val
            }
        }
    }
}

$VenvPython = Join-Path $PSScriptRoot ".." ".venv" "Scripts" "huaweicloud-mcp-server.exe"
$VenvPython = [System.IO.Path]::GetFullPath($VenvPython)

if (Test-Path $VenvPython) {
    & $VenvPython @args
} else {
    # Fallback: uv run
    uv run huaweicloud-mcp-server @args
}
