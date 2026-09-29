# Candidate confidence bands

When a `TemplateSpec` contains an explicit `fit_request` for a marker-derived
linear, Boltzmann, or 4PL curve, preparation estimates a parameter covariance
from the visible placeholder markers. If that covariance is finite, the fit
trace receives `FitLower` and `FitUpper` columns in the same `Reference Data`
worksheet. Origin renders these columns as two linked line plots with a
fill-to-next-data-plot region, so the band remains editable after replacement.

The default level is 95%; set `confidence_level` between 0.5 and 1.0 in the
fit request to choose another candidate level. The metadata records the level,
degrees of freedom, critical value, and `delta_method_parameter_covariance`.
This is a visual placeholder around the candidate fit, not a reconstruction of
the paper's confidence interval. If covariance is unavailable, the plugin
keeps the fit line and omits the band rather than fabricating uncertainty.
After replacing X/Y values, recompute both bounds with the user's own model,
replicate structure, and uncertainty method.
