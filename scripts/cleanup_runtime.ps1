[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [string]$Version,
    [switch]$All
)

$ErrorActionPreference = "Stop"
$dataRoot = $env:PLUGIN_DATA
if ([string]::IsNullOrWhiteSpace($dataRoot)) {
    $localAppData = $env:LOCALAPPDATA
    if ([string]::IsNullOrWhiteSpace($localAppData)) { $localAppData = [IO.Path]::GetTempPath() }
    $dataRoot = Join-Path $localAppData "fig-brush"
}
$runtimeRoot = Join-Path $dataRoot "runtimes"
if (-not (Test-Path -LiteralPath $runtimeRoot)) {
    Write-Host "No fig-brush runtimes found under $runtimeRoot"
    exit 0
}

if ($All -and -not [string]::IsNullOrWhiteSpace($Version)) {
    throw "Use either -All or -Version, not both."
}
$targets = if ($All) {
    @(Get-ChildItem -LiteralPath $runtimeRoot -Directory)
} elseif (-not [string]::IsNullOrWhiteSpace($Version)) {
    $candidate = Join-Path $runtimeRoot $Version
    if (Test-Path -LiteralPath $candidate) { @(Get-Item -LiteralPath $candidate) } else { @() }
} else {
    @(Get-ChildItem -LiteralPath $runtimeRoot -Directory)
}

if ($targets.Count -eq 0) {
    Write-Host "No matching fig-brush runtimes found under $runtimeRoot"
    exit 0
}
if (-not $All -and [string]::IsNullOrWhiteSpace($Version)) {
    Write-Host "Installed fig-brush runtimes:"
    $targets | ForEach-Object { Write-Host " - $($_.Name) ($($_.FullName))" }
    Write-Host "Pass -Version <version> or -All with -Confirm to remove runtime folders."
    exit 0
}

foreach ($target in $targets) {
    if ($PSCmdlet.ShouldProcess($target.FullName, "Remove fig-brush runtime")) {
        Remove-Item -LiteralPath $target.FullName -Recurse -Force
        Write-Host "Removed $($target.FullName)"
    }
}
