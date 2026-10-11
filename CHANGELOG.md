# Changelog

All notable changes to fig-brush are recorded here. The project follows
semantic versioning for public releases.

## [0.3.2] - 2026-09-30

### Added

- A repo-scoped Codex marketplace entry for local installation.
- A per-user, versioned runtime bootstrap that works from Codex's installed
  plugin cache copy.
- `scripts/doctor.py` for dependency and Origin capability diagnostics.
- `scripts/check_mcp.py` for initialize/tools-list/stdout protocol smoke tests.
- `scripts/check_origin_roundtrip.py` for native Origin save/reopen persistence
  checks on a copied project.
- `scripts/cleanup_runtime.ps1` for safe removal of unused plugin runtimes.

### Changed

- MCP startup diagnostics stay on stderr so stdout remains reserved for the
  stdio protocol.
- Release metadata, documentation, and generated examples now identify the
  `0.3.2` release.

## [0.3.1] - 2026-09-29

### Added

- A `fig-brush` Python package and command entry point.
- Screenshot-first reference inspection and editable Origin template output.
- Explicit visual placeholder policy and replacement manifests.
- Candidate linear, Boltzmann, and 4PL fit traces with replacement guidance.
- Structured scientific reconstruction fields for mark roles, line semantics,
  uncertainty, typography, and worksheet layout.
- Text-layout, error-bar, pie/doughnut, heatmap, and confidence-band support.
- Windows setup and MCP launch scripts using a project-local `.venv`.
- Public synthetic example assets and CI validation for tests, manifests, and
  plugin packaging.

### Notes

- Placeholder values are visual aids and are not recovered research data.
- Native `.opju` rendering requires a separately licensed Origin installation
  and a compatible separately distributed `originpro` package.
- The screenshot-only path does not require a private CSV/XLSX dataset.

## [0.3.3] - 2026-10-11

- Mixed column and marker panels now preserve independent marker X columns
  while retaining a shared categorical grid for native bar widths.
- Added `style.bar_gap_percent` for reproducible native Origin bar spacing.
- Origin UFF/COM startup failures now explain the one-time UFF setup and the
  effects of the `-d` reset switch; preview exports close their COM session.
- Prepared templates now include conventional `Raw_Data`, `Summary_Data`, or
  `XY_Data` inputs, a replacement contract, and a local refresh tool that
  rebuilds the same visual style without inferring statistics.
- Added the compact `format_brush` entry point and `format-brush` CLI command.
  They write `APPLY_FORMAT.md`, `format_parameters.json`, and
  `reference_analysis.json` by default, with no Origin project or research
  data. Added `apply_format`/`apply-format` to save a styled copy of an
  existing Origin project without overwriting it.
- Added `apply_active_format` for applying a bundle to the graph already open
  in Origin, plus `stage_format_clipboard` for preparing Origin's native
  Copy Format/Paste Format workflow from a reference `.opju`/`.opj`.
- The generated apply guide now treats JSON as an internal contract and gives
  users a no-script Codex path first; the optional Origin `.opx` right-click
  wrapper still needs version-specific desktop packaging and validation.
- Product direction is now explicitly reference-image-to-format-parameters
  first. Native `style_template.otpu` export and the synthetic `result.opju`
  remain optional compatibility outputs, while local data replacement stays
  opt-in.
