# Keep stdout reserved for the MCP protocol. Runtime bootstrap diagnostics go
# to stderr through ensure_runtime.ps1.
$ErrorActionPreference = "Stop"
$pluginRoot = Split-Path -Parent $PSScriptRoot
$venvPython = & (Join-Path $PSScriptRoot "ensure_runtime.ps1") -PluginRoot $pluginRoot
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($venvPython)) { exit 2 }
$env:PYTHONUTF8 = "1"
Push-Location -LiteralPath $pluginRoot
try {
    & $venvPython -m fig_brush
    $serverExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $serverExitCode
