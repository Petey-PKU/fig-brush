# Keep stdout reserved for the MCP protocol. No automatic installs at startup.
$ErrorActionPreference = "Stop"
$pluginRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $pluginRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    [Console]::Error.WriteLine("fig-brush: run scripts/setup.ps1 in the plugin folder before starting the MCP server.")
    exit 2
}
$env:PYTHONUTF8 = "1"
Push-Location -LiteralPath $pluginRoot
try {
    & $venvPython -m fig_brush
    $serverExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $serverExitCode
