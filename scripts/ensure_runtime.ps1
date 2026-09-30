[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PluginRoot,
    [string]$Python = "python",
    [switch]$Dev
)

# Resolve a per-user runtime for the installed plugin copy. Codex installs a
# marketplace plugin into its cache, so a .venv created in the source checkout
# is not necessarily next to the copy that Codex launches.
$ErrorActionPreference = "Stop"
$pluginRoot = (Resolve-Path -LiteralPath $PluginRoot).Path
$manifestPath = Join-Path $pluginRoot ".codex-plugin\plugin.json"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    [Console]::Error.WriteLine("fig-brush: .codex-plugin/plugin.json was not found under $pluginRoot")
    exit 2
}

try {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $version = [string]$manifest.version
    if ([string]::IsNullOrWhiteSpace($version)) { throw "manifest version is empty" }
} catch {
    [Console]::Error.WriteLine("fig-brush: could not read the plugin manifest: $($_.Exception.Message)")
    exit 2
}

$dataRoot = $env:PLUGIN_DATA
if ([string]::IsNullOrWhiteSpace($dataRoot)) {
    $localAppData = $env:LOCALAPPDATA
    if ([string]::IsNullOrWhiteSpace($localAppData)) { $localAppData = [IO.Path]::GetTempPath() }
    $dataRoot = Join-Path $localAppData "fig-brush"
}
$runtimeRoot = Join-Path $dataRoot "runtimes"
$runtimeDir = Join-Path $runtimeRoot $version
$venvPython = Join-Path $runtimeDir "Scripts\python.exe"
$markerPath = Join-Path $runtimeDir "install.json"
$lockPath = Join-Path $runtimeRoot "$version.lock"

function Get-SourceFingerprint {
    $rows = [Collections.Generic.List[string]]::new()
    $files = Get-ChildItem -LiteralPath $pluginRoot -Recurse -File | Sort-Object FullName
    $runtimePrefix = [IO.Path]::GetFullPath($runtimeRoot).TrimEnd('\') + '\'
    foreach ($file in $files) {
        $fullPath = [IO.Path]::GetFullPath($file.FullName)
        if ($fullPath.StartsWith($runtimePrefix, [StringComparison]::OrdinalIgnoreCase)) { continue }
        $relative = $file.FullName.Substring($pluginRoot.Length).TrimStart('\').Replace('\', '/')
        $parts = $relative.Split('/')
        $eggInfoPart = $parts | Where-Object { $_ -like "*.egg-info" }
        if ($parts -contains ".git" -or $parts -contains ".venv" -or
            $parts -contains "dist" -or $parts -contains "outputs" -or
            $parts -contains "build" -or $parts -contains "__pycache__" -or
            $null -ne $eggInfoPart) { continue }
        if ($file.Extension.ToLowerInvariant() -notin @(".py", ".json", ".md", ".ps1", ".toml", ".txt")) { continue }
        $digest = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
        $rows.Add("$relative=$digest") | Out-Null
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes(($rows -join "`n"))
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

$sourceFingerprint = Get-SourceFingerprint

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
$lock = $null
try {
    # Avoid two Codex sessions installing the same runtime concurrently.
    for ($attempt = 0; $attempt -lt 120 -and $null -eq $lock; $attempt++) {
        try {
            $lock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        } catch [IO.IOException] {
            Start-Sleep -Milliseconds 500
        }
    }
    if ($null -eq $lock) {
        [Console]::Error.WriteLine("fig-brush: timed out waiting for the runtime install lock: $lockPath")
        exit 2
    }

    $needsInstall = -not (Test-Path -LiteralPath $venvPython) -or -not (Test-Path -LiteralPath $markerPath)
    if (-not $needsInstall) {
        try {
            $installed = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
            $needsInstall = ([string]$installed.version -ne $version) -or
                ([string]$installed.sourceFingerprint -ne $sourceFingerprint)
        } catch {
            $needsInstall = $true
        }
    }

    if ($needsInstall) {
        $bootstrapPython = Get-Command $Python -ErrorAction SilentlyContinue
        if ($null -eq $bootstrapPython) {
            [Console]::Error.WriteLine("fig-brush: Python 3.10 or newer is required to create the local runtime: $Python")
            exit 2
        }
        if (-not (Test-Path -LiteralPath $venvPython)) {
            New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
            [Console]::Error.WriteLine("fig-brush: creating runtime $runtimeDir")
            & $bootstrapPython.Source -m venv $runtimeDir 2>&1 | ForEach-Object { [Console]::Error.WriteLine([string]$_) }
            $venvExitCode = $LASTEXITCODE
            if ($venvExitCode -ne 0) { throw "Python could not create the virtual environment." }
        }
        [Console]::Error.WriteLine("fig-brush: installing dependencies for version $version")
        # Build from a writable runtime staging copy. Setuptools can create
        # build/ and *.egg-info/ beside pyproject.toml, while a Codex cache
        # checkout may be read-only and should remain free of generated files.
        $stagingDir = Join-Path $runtimeDir ".package-source"
        if (Test-Path -LiteralPath $stagingDir) {
            Remove-Item -LiteralPath $stagingDir -Recurse -Force
        }
        New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null
        try {
            foreach ($item in @("pyproject.toml", "README.md", "requirements.txt", "fig_brush", "mcp_server", "origin_bridge", "plot_specs", "templates")) {
                $source = Join-Path $pluginRoot $item
                if (-not (Test-Path -LiteralPath $source)) { throw "required package source is missing: $item" }
                Copy-Item -LiteralPath $source -Destination $stagingDir -Recurse -Force
            }
            $installTarget = $stagingDir
            if ($Dev) { $installTarget = "${stagingDir}[dev]" }
            & $venvPython -m pip install --disable-pip-version-check --no-input --upgrade $installTarget 2>&1 | ForEach-Object { [Console]::Error.WriteLine([string]$_) }
            $pipExitCode = $LASTEXITCODE
            if ($pipExitCode -ne 0) { throw "pip could not install the plugin and its dependencies." }
        } finally {
            if (Test-Path -LiteralPath $stagingDir) {
                Remove-Item -LiteralPath $stagingDir -Recurse -Force
            }
        }
        @{ name = "fig-brush"; version = $version; sourceFingerprint = $sourceFingerprint; pluginRoot = $pluginRoot; installedAtUtc = [DateTime]::UtcNow.ToString("o") } |
            ConvertTo-Json | Set-Content -LiteralPath $markerPath -Encoding UTF8
    }

    # Stdout is intentionally only the executable path. The MCP protocol uses
    # stdout, while bootstrap diagnostics are written to stderr above.
    Write-Output $venvPython
} catch {
    [Console]::Error.WriteLine("fig-brush: runtime setup failed: $($_.Exception.Message)")
    exit 2
} finally {
    if ($null -ne $lock) { $lock.Dispose() }
}
