[CmdletBinding()]
param(
    [string]$Python = "python",
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$pluginRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $pluginRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $Python -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment. Use Python 3.10 or newer." }
}

$installTarget = $pluginRoot
if ($Dev) { $installTarget = "${pluginRoot}[dev]" }
& $venvPython -m pip install $installTarget
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

Write-Host "fig-brush is installed in its local .venv."
Write-Host "For native rendering, install licensed Origin separately and install originpro in this environment."
Write-Host "Then configure the local plugin as described in docs/installation.md."
