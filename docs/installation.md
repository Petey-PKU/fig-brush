# Installation

fig-brush is developed for Windows because native Origin automation uses the
local Origin application. The screenshot-template preparation path can be
run without Origin; native `.opju` rendering cannot.

## Requirements

- Windows 10 or 11;
- Python 3.10 or newer;
- Origin 2021 or newer with a valid local license for native rendering;
- the separately distributed `originpro` package in the same Python
  environment as the MCP server when Origin automation is required.

Origin and OriginLab are third-party commercial products. fig-brush does not
include or grant an Origin license. `originpro` is a separately distributed
third-party Python package; follow the terms and installation instructions for
the version selected for your Origin installation.

## Install from a checkout

Open PowerShell in the repository root and run:

```powershell
.\scripts\setup.ps1
```

The script creates `.venv` and installs the local `fig-brush` package into it.
For development and tests, use:

```powershell
.\scripts\setup.ps1 -Dev
```

For a GitHub release, download `fig-brush-<version>.zip` and its SHA-256
sidecar from the release page, extract the archive, and run the same script
from the extracted directory containing `.codex-plugin`. Do not delete that
directory while the local Codex plugin is enabled because its MCP launcher is
started from the checkout.

On Windows, compare the downloaded archive before extraction:

```powershell
Get-FileHash .\fig-brush-<version>.zip -Algorithm SHA256
Get-Content .\fig-brush-<version>.zip.sha256
```

When native rendering is needed, install `originpro` into this same
environment using its supported package instructions. Do not install it into a
different global Python and expect the MCP server to find it.

## Health check

```powershell
.\.venv\Scripts\python.exe -c "from origin_bridge.connection import origin_status; print(origin_status())"
```

The result should report an available local Origin session before a native
render. A missing Origin installation is reported as an unavailable bridge;
fig-brush does not fabricate an `.opju` in that case.

## Screenshot-only workflow

Use `inspect_reference` on a PNG or JPEG, complete the visual reading as a
`TemplateSpec`, then call `prepare_reference_template`. The output includes a
template specification, a data manifest, previews, and (when Origin is
available) an editable project. Workbook values are synthetic visual
placeholders. Replace them with your own research values in Origin.

The screenshot workflow does not upload or require a private dataset. The
Codex host/model may process the screenshot and tool results under its own
policies, so do not assume that this means every deployment is offline. An
older compatibility/data-inspection tool may read a CSV or XLSX path only when
the user explicitly supplies that path.

## MCP launch

After setup, the repository `.mcp.json` starts:

```powershell
.\scripts\run_mcp.ps1
```

The launcher checks for `.venv\Scripts\python.exe`, changes to the plugin
root, and runs `python -m fig_brush`. It keeps stdout reserved for MCP
messages. Run the setup script first; the launcher does not install packages
at startup.

## Synthetic example

The public synthetic example can be prepared without Origin:

```powershell
.\.venv\Scripts\python.exe examples\synthetic\run_example.py
```

Pass `--render-origin` only after installing and licensing Origin and adding
`originpro` to `.venv`.
