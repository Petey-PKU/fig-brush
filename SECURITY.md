# Security policy

## Supported versions

Security fixes are expected for the latest `0.3.x` release. Older releases
may not receive fixes; update to the newest release before reporting a problem.

## Reporting a vulnerability

Please do not disclose an exploitable vulnerability in a public issue or pull
request. If private vulnerability reporting is enabled for the repository, use
that channel. Otherwise contact the maintainer through the repository owner's
private contact channel and include:

- the affected fig-brush version and operating system;
- a minimal reproduction or proof of concept;
- whether Origin or `originpro` is involved;
- the impact and any suggested mitigation.

Do not include private research images, CSV/XLSX files, credentials, or
proprietary `.opju` projects in a report. Redact paths and data before sharing.

The maintainer will acknowledge a report when practical, investigate it, and
coordinate a fix or mitigation. Please allow time for a fix before public
disclosure.

## Scope notes

fig-brush may receive a screenshot and may invoke a local Origin process. The
Codex host/model can process screenshots and tool results according to its own
policies. A local Origin installation and the third-party `originpro` package
are outside this repository's control; report their vulnerabilities to their
respective vendors as well.
