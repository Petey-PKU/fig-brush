from mcp_server.inference import _family_from_notes, infer_plot_spec


def _inventory():
    return {
        "file": "data.csv",
        "tables": [
            {
                "name": "data",
                "columns": [
                    {"name": "Group", "is_numeric": False},
                    {"name": "Value", "is_numeric": True},
                ],
                "candidate_models": [
                    {"data_model": "long_grouped", "confidence": 0.72}
                ],
            }
        ],
    }


def test_inference_asks_for_ambiguous_error_bar_and_graph_family():
    result = infer_plot_spec(None, _inventory())

    assert result["status"] == "needs_clarification"
    assert result["plot_spec"]["graph_family"] == "column"
    assert len(result["clarification_questions"]) >= 2


def test_explicit_reference_can_make_inference_ready():
    reference = {
        "reference_spec": {
            "graph_family": "scatter",
            "data_model": "xy_or_wide_numeric",
            "confidence": 0.96,
            "style": {"raw_points": True},
        }
    }
    inventory = {
        "file": "data.csv",
        "tables": [
            {
                "name": "data",
                "columns": [
                    {"name": "X", "is_numeric": True},
                    {"name": "Y", "is_numeric": True},
                ],
                "candidate_models": [
                    {"data_model": "xy_or_wide_numeric", "confidence": 0.68}
                ],
            }
        ],
    }

    result = infer_plot_spec(reference, inventory)

    assert result["status"] == "ready"
    assert result["plot_spec"]["data_mapping"]["x"] == "X"
    assert result["plot_spec"]["data_mapping"]["y"] == "Y"
    assert result["plot_spec"]["data_mapping"]["numeric_columns"] == ["Y"]


def test_measured_axis_tick_hints_override_visual_guess():
    reference = {
        "reference_spec": {
            "graph_family": "line",
            "confidence": 0.96,
            "style": {
                "x_major_tick_count_hint": 8,
                "x_minor_tick_count_hint": 1,
                "y_major_tick_count_hint": 5,
                "y_minor_tick_count_hint": 4,
            },
            # Simulate a model that guessed the same number of minor ticks on
            # both axes.  The measured image evidence must win.
            "axes": {
                "x": {"minor_tick_count": 4},
                "y": {"minor_tick_count": 4},
            },
        }
    }
    inventory = {
        "file": "data.csv",
        "tables": [
            {
                "name": "data",
                "columns": [
                    {"name": "X", "is_numeric": True},
                    {"name": "Y", "is_numeric": True},
                ],
                "candidate_models": [{"data_model": "xy_or_wide_numeric", "confidence": 0.9}],
            }
        ],
    }

    result = infer_plot_spec(reference, inventory)

    assert result["plot_spec"]["axes"]["x"]["minor_tick_count"] == 1
    assert result["plot_spec"]["axes"]["y"]["minor_tick_count"] == 4


def test_reference_context_is_kept_separate_and_unresolved_context_is_asked_for():
    reference = {
        "reference_spec": {
            "graph_family": "line",
            "scientific_context": {
                "reference": {
                    "research_question": None,
                    "uncertainty": "unknown",
                    "encodings": [],
                    "annotations": [],
                    "unresolved": [],
                }
            },
        }
    }
    result = infer_plot_spec(reference, _inventory())

    assert result["status"] == "needs_clarification"
    assert "scientific_context" in result["plot_spec"]["interpretation"]
    assert any("研究问题" in question for question in result["clarification_questions"])


def test_specific_regression_note_wins_over_generic_line_token():
    assert _family_from_notes("show a regression line with confidence band") == "regression"


def test_explicit_pie_variants_win_over_bar_and_plain_pie_tokens():
    assert _family_from_notes("pie 3d with error bars") == "pie3d"
    assert _family_from_notes("3d-pie") == "pie3d"
    assert _family_from_notes("doughnut3d with bars") == "doughnut3d"
    assert _family_from_notes("pie with error bars") == "pie"
