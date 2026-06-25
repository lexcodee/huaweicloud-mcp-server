# Strategy 1 deployment: single mount /hwc, all Huawei Cloud tools in one place.
#
# Starts the mcp-gateway with the unified manifest. Agents connect to
# http://127.0.0.1:8080/hwc/sse and see all enabled tools (ecs_*, pipeline_*,
# cts_*) in one list.
#
# Env vars consumed via .env:
#   HUAWEICLOUD_AK / SK / PROJECT_ID / REGION  (passed to huaweicloud_mcp)
#   MCP_JWT_PUBLIC_KEY                          (gateway JWT)
#   MCP_GATEWAY_AUTH                            (set to "disabled" for dev)
#   MCP_GATEWAY_PORT                            (default 8080)
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Load .env if present
$EnvFile = Join-Path $ScriptDir ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line -split "=", 2
            if ($parts.Length -eq 2) {
                $key = $parts[0].Trim()
                $val = $parts[1].Trim()
                if ($val.StartsWith('"') -and $val.EndsWith('"')) { $val = $val.Substring(1, $val.Length - 2) }
                if ($val.StartsWith("'") -and $val.EndsWith("'")) { $val = $val.Substring(1, $val.Length - 2) }
                Set-Item -Path "env:$key" -Value $val
            }
        }
    }
}

$Manifest = Join-Path $ScriptDir "manifest.yaml"
$Port = if ($env:MCP_GATEWAY_PORT) { $env:MCP_GATEWAY_PORT } else { "8080" }
$Host_ = if ($env:MCP_GATEWAY_HOST) { $env:MCP_GATEWAY_HOST } else { "127.0.0.1" }
$LogLevel = if ($env:MCP_GATEWAY_LOG_LEVEL) { $env:MCP_GATEWAY_LOG_LEVEL } else { "info" }

uv run mcp-gateway serve `
    --manifest $Manifest `
    --port $Port `
    --host $Host_ `
    --log-level $LogLevel `
    @args
