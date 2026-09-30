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

## [Unreleased]

Future changes will be listed here before the next release.
