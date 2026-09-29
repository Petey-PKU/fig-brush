# Text layout contract (0.3.1)

`origin_bridge.text_layout.layout_text_label` places an already-created Origin
label after its rich text has been assigned. It reads the rendered label's
`x`, `y`, `dx`, and `dy`, so superscripts, subscripts, and multiple lines use
their actual Origin bounding box rather than hand-tuned offsets.

```python
from origin_bridge.text_layout import TextLayout, layout_text_label

layout_text_label(
    label,
    TextLayout(
        x=5.0, y=20.0, coordinate_space="data",
        h_anchor="center", v_anchor="middle",
        paragraph_align="center", rotation=90,
    ),
)
```

Data coordinates use `attach=2`; `x1/y1` are calculated in axis units. Page
coordinates use `attach=1` and page fractions with a top-left origin. Page
placement must receive either a measured `size_fraction` or a
`FrameGeometry` containing the plot frame and both axis transforms. The latter
supports logarithmic axes without treating equal pixel widths as equal data
widths. If geometry is missing, the function raises instead of guessing.

Origin's GObject documentation defines `x/y` as the center of the invisible
object rectangle and `dx/dy` as its dimensions. `attach=1` makes `x1/y1` page
fractions while `attach=2` makes them axis coordinates. See the
[Graphic Objects reference](https://docs.originlab.com/labtalk/ref/graphic-objs/)
and [label justification](https://docs.originlab.com/labtalk/ref/label-cmd/).

Template labels may use `text_markup` (or the shorter `markup`) when the
reader has recovered Origin rich text. Plain `text` is also accepted: the
bridge converts existing Unicode superscript/subscript runs such as `CD8⁺`
and `PEPRA₍EE₎` to `\\+(...)`/`\\-(...)` before measuring the object. This
keeps glyph baselines and measured widths stable across preview resolutions.
`anchor`/`text_anchor` accepts `center`, `top_left`, `top_center`,
`top_right`, `bottom_left`, `bottom_center`, and `bottom_right` aliases.


