# Troubleshooting

## `originpro` is unavailable

Install Origin 2021 or newer, make sure it is licensed, and install OriginLab's
`originpro` package in the same Python environment used by the MCP server only
when native export is requested. The default `format_brush` parameter workflow
does not need Origin.

## Origin shows the User Files Folder dialog

Origin asks for a User Files Folder (UFF) the first time its desktop or COM
automation is initialized. Complete that dialog once in the normal Origin
desktop and choose a writable local folder, such as the default Documents
location. The UFF stores Origin configuration files; it is separate from the
project output folder, so fig-brush can continue to save `result.opju` and
previews under the requested project `test` directory.

If you are only checking screenshot measurements, call `format_brush`; this
path never starts Origin and writes the two JSON artifacts plus the
`APPLY_FORMAT.md` checklist directly to the requested output folder. If you
already have an `.opju`, use `apply-format` with `format_parameters.json` to
create a formatted copy. A native `.otpu` cannot be created without starting
Origin at least once, because Origin itself owns the template format.

Do not start `Origin64.exe` with `-d` during ordinary generation. That switch
intentionally forces Origin to select a new UFF and makes the dialog reappear.
If the diagnostic says that Origin Automation connected but could not finish
startup, allow COM and registry access for the desktop process or run the
native render outside a restricted sandbox. The plugin reports this condition
instead of silently producing a non-native placeholder file.

## The preview does not align with the reference

Use `compare_reference` and inspect its overlay. Correct one image at a time:
frame margins, axis limits and ticks, title offsets, font sizes, legend rows,
then curve and marker coordinates. Do not use a private dataset to solve a
visual mismatch; the placeholder worksheets are intentionally local and
replaceable.

## A graph template cannot be loaded

Set `style.origin_template` to a template name present in the local Origin
installation, or use the default family template and rerun verification.

## Verification reports Origin as skipped

The source and template checks can still run, but the native project has not
been opened. Start Origin and rerun the verification command before delivering
the `.opju`.
