# Troubleshooting

## `originpro` is unavailable

Install Origin 2021 or newer, make sure it is licensed, and install OriginLab's
`originpro` package in the same Python environment used by the MCP server. The
plugin reports the failure instead of fabricating an `.opju`.

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
