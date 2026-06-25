# Delegate to the workspace-root start.ps1.
# This wrapper exists so `cd mcp-gateway; powershell -File scripts/start.ps1` still works,
# but the real logic lives in one place.
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Root = Split-Path -Parent (Split-Path -Parent $ScriptDir)

& (Join-Path $Root "start.ps1") @args
