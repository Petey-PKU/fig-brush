import pandas as pd

from mcp_server.data_inspector import inspect_dataset
from mcp_server.inference import infer_plot_spec
from mcp_server.semantic_analysis import analyze_dataframe


def test_ordered_signal_is_read_as_a_trace_with_peak_evidence():
    frame = pd.DataFrame(
        {
            "m/z": [100, 101, 102, 103, 104, 105, 106, 107],
            "intensity": [1, 2, 8, 3, 1, 2, 6, 1],
        }
    )
    result = analyze_dataframe(frame, "spectrum")

    assert result["data_model"] == "ordered_xy_series"
    assert result["recommended_graph"]["graph_family"] == "line"
    assert result["mapping"]["x"] == "m/z"
    assert result["mapping"]["y"] == "intensity"
    assert result["signal_findings"][0]["x"] == "m/z"
    assert result["signal_findings"][0]["maximum_observed"]["x"] == 102.0
    assert "local_maximum_candidates" in result["signal_findings"][0]
    assert result["error_structure"]["inferred_error_type"] is None


def test_grouped_repeats_are_distribution_data_not_just_bars():
    frame = pd.DataFrame(
        {
            "Condition": ["A", "A", "A", "B", "B", "B"],
            "Response": [1.0, 1.2, 0.9, 2.0, 2.1, 1.8],
        }
    )
    result = analyze_dataframe(frame, "assay")

    families = [candidate["graph_family"] for candidate in result["candidate_graphs"]]
    assert result["data_model"] == "long_repeated_observations"
    assert "box" in families
    assert result["recommended_graph"]["graph_family"] == "box"


def test_error_columns_are_evidence_and_not_measurement_series():
    frame = pd.DataFrame(
        {
            "Condition": ["A", "B"],
            "Mean": [1.0, 2.0],
            "SD": [0.1, 0.2],
            "CI95": [0.2, 0.3],
        }
    )
    result = analyze_dataframe(frame, "summary")

    assert result["error_structure"]["columns"]["sd"] == ["SD"]
    assert result["error_structure"]["columns"]["ci"] == ["CI95"]
    assert result["representation"] == "summary_values"
    assert "SD" not in result["mapping"]["values"]
    assert "CI95" not in result["mapping"]["values"]


def test_heatmap_requires_explicit_matrix_context():
    frame = pd.DataFrame({f"z{i}": [i + j for j in range(4)] for i in range(4)})
    result = analyze_dataframe(frame, "correlation_matrix")

    assert result["data_model"] == "numeric_matrix"
    assert result["recommended_graph"]["graph_family"] == "heatmap"
    assert result["mapping"]["matrix_columns"] == ["z0", "z1", "z2", "z3"]


def test_inspection_exposes_semantic_analysis_for_downstream_inference(workspace_tmp):
    path = workspace_tmp / "signal.csv"
    path.write_text("Time,Signal\n0,0\n1,2\n2,1\n", encoding="utf-8")

    inventory = inspect_dataset(path)
    semantic = inventory["tables"][0]["semantic_analysis"]

    assert semantic["analysis_version"] == "0.2"
    assert semantic["recommended_graph"]["graph_family"] == "line"
    assert semantic["scientific_question"]["intent"] == "progression_or_spectrum"

    inferred = infer_plot_spec(None, inventory)
    assert inferred["plot_spec"]["interpretation"]["data_model"] == "ordered_xy_series"
