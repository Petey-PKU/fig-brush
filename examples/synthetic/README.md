# Synthetic example

This example is generated locally and contains no private measurements or
paper figures. `reference.png` is a deterministic two-series line-and-scatter
image. `template_spec.json` contains the visual contract that fig-brush uses to
build an editable Origin template.

From any working directory, run:

```powershell
python path\to\fig-brush\examples\synthetic\generate_reference.py
python path\to\fig-brush\examples\synthetic\run_example.py
```

The second command writes a reference-only preparation to
`fig-brush/outputs/synthetic` and does not start Origin. Add `--render-origin`
when a supported local Origin installation is available.

Every value here is a visual placeholder, not original research data.
