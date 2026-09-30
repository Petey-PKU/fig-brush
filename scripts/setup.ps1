[CmdletBinding()]
param(
    [string]$Python = "python",
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$pluginRoot = Split-Path -Parent $PSScriptRoot
$venvPython = & (Join-Path $PSScriptRoot "ensure_runtime.ps1") -PluginRoot $pluginRoot -Python $Python -Dev:$Dev
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($venvPython)) { throw "Dependency installation failed." }

Write-Host "fig-brush is installed in the per-user runtime: $venvPython"
Write-Host "For native rendering, install licensed Origin separately and install originpro in this environment."
Write-Host "Then enable the local Codex marketplace as described in docs/installation.md."
