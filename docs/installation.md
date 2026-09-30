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

The script creates a versioned, per-user runtime under
`%LOCALAPPDATA%\fig-brush\runtimes` (or `PLUGIN_DATA` when Codex provides it)
and installs the local `fig-brush` package there. For development and tests,
use:

```powershell
.\scripts\setup.ps1 -Dev
```

For a GitHub release, download `fig-brush-<version>.zip` and its SHA-256
sidecar from the release page, extract the archive, and run the same script
from the extracted directory containing `.codex-plugin`. The MCP launcher can
also bootstrap the per-user runtime from the installed marketplace copy on its
first start.

## Register the local Codex marketplace

The repository contains `.agents/plugins/marketplace.json`, a repo-scoped
marketplace whose `fig-brush` entry points at this checkout. Register the
repository root as a local marketplace after setup:

```powershell
codex plugin marketplace add "C:\path\to\fig-brush"
codex plugin marketplace list
```

In Codex, open the Plugins Directory, choose **fig-brush Local**, and install
`fig-brush`. Start a new chat after installation. Keep the checkout available
as the marketplace source so Codex can refresh it when you upgrade.

After pulling or checking out a new version, refresh the registered marketplace
and restart Codex if needed:

```powershell
codex plugin marketplace upgrade fig-brush-local
```

To uninstall the plugin, remove `fig-brush` from the Plugins Directory. When
the repository should no longer be registered as a source, remove the
marketplace as well:

```powershell
codex plugin marketplace remove fig-brush-local
```

Marketplace upgrades use a new versioned runtime. After uninstalling the
plugin, inspect or remove only those runtimes with the bundled cleanup script;
it never touches generated projects or research data:

```powershell
.\scripts\cleanup_runtime.ps1
.\scripts\cleanup_runtime.ps1 -Version 0.3.2 -Confirm
# or, after all fig-brush installations are removed:
.\scripts\cleanup_runtime.ps1 -All -Confirm
```

On Windows, compare the downloaded archive before extraction:

```powershell
Get-FileHash .\fig-brush-<version>.zip -Algorithm SHA256
Get-Content .\fig-brush-<version>.zip.sha256
```

When native rendering is needed, install `originpro` into the per-user runtime
using its supported package instructions. Use the runtime Python printed by
`setup.ps1`; do not install it into a different global Python and expect the
MCP server to find it.

## Health check

Run the bundled doctor with the same Python environment used by the MCP
launcher:

```powershell
$python = .\scripts\ensure_runtime.ps1 -PluginRoot .
& $python scripts\doctor.py --plugin-root .
& $python scripts\check_mcp.py --plugin-root . --python $python
```

The doctor checks Python 3.10+, the plugin manifest, packaged imports, the
Windows platform, and the `originpro` import. It only inspects the Origin API
entry points; it does not start Origin, create a project, open a file, or save
anything. Use `--json` for automation:

```powershell
& $python scripts\doctor.py --plugin-root . --json
```

Exit code `0` means the screenshot-template workflow is ready. Origin is an
optional local capability, so a missing or unavailable Origin installation is
shown as a warning and still returns `0`; use `--require-origin` when a native
`.opju` render is a prerequisite. The MCP probe performs a real `initialize`,
`tools/list`, and harmless `origin_status_tool` call. Exit code `1` indicates
a missing plugin root, unsupported Python, missing/broken packaged dependency,
or an MCP protocol failure.

After preparing a native `.opju`, verify persistence on a copy of that project:

```powershell
& $python scripts\check_origin_roundtrip.py .\outputs\synthetic\result.opju
```

This probe changes one numeric worksheet cell in the copy, saves and reopens
it, and checks that the value and a graph page persist. It never changes the
input project.

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

The launcher resolves the installed plugin root, creates or reuses the
versioned per-user runtime, changes to the plugin root, and runs
`python -m fig_brush`. It keeps stdout reserved for MCP messages. Running
`setup.ps1` before opening Codex avoids first-use installation delay, while the
launcher can bootstrap a missing runtime itself.

## Synthetic example

The public synthetic example can be prepared without Origin:

```powershell
$python = .\scripts\ensure_runtime.ps1 -PluginRoot .
& $python examples\synthetic\run_example.py
```

Pass `--render-origin` only after installing and licensing Origin and adding
`originpro` to the per-user runtime.
