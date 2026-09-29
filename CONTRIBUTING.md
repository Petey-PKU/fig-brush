# Contributing to fig-brush

Thank you for helping improve fig-brush. Contributions should keep the
reference-first workflow honest: visible geometry may be approximated, but
placeholder values must never be presented as recovered measurements.

## Development setup

Use Windows with Python 3.10 or newer:

```powershell
.\scripts\setup.ps1 -Dev
.\.venv\Scripts\python.exe -m pytest
```

The optional native rendering checks require a licensed local Origin and a
compatible `originpro` installation. Tests that do not need Origin should
remain runnable without it.

## Making a change

1. Describe the user-visible behavior and the scientific interpretation it
   preserves.
2. Keep public APIs and manifest fields documented.
3. Add or update focused tests for behavior that can be verified without
   Origin.
4. Use synthetic examples or generated fixtures. Do not add private datasets,
   paper screenshots, `.opju` files, or files whose redistribution rights are
   unclear.
5. Run the test suite and the plugin packaging command before opening a pull
   request:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest
   python scripts\package_plugin.py
   ```

## Pull requests

Explain the problem, the resulting behavior, and validation performed. Call
out any Origin-version limitation or change to placeholder semantics. Keep
commits focused and avoid committing generated caches, local paths, or
credentials.

## Documentation and examples

Documentation is written in English. Examples must state when values are
synthetic visual placeholders. If a change touches screenshot handling,
describe whether the workflow reads any user-supplied CSV/XLSX path and keep
the screenshot-only path independent of private data.

By contributing, you agree that your work is provided under the repository's
[Apache License 2.0](LICENSE).
