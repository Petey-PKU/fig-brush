import json

from mcp_server.replacement import build_replacement_bundle, refresh_reference_spec


def test_categorical_reference_writes_scientific_input_tables(tmp_path):
    spec = {
        "panels": [{
            "id": "Main",
            "labels": [{"text": "Control"}, {"text": "Drug"}],
            "series": [
                {"id": "ControlBar", "name": "Control", "kind": "column", "data": {
                    "x": [1, 2], "y": [10, 0], "y_error": [2, 0]}},
                {"id": "DrugBar", "name": "Drug", "kind": "column", "data": {
                    "x": [1, 2], "y": [0, 20], "y_error": [0, 3]}},
                {"id": "ControlReplicates", "name": "Control replicates", "kind": "scatter",
                 "role": "raw replicate markers", "data": {"x": [0.9, 1.1], "y": [9, 11]}},
                {"id": "DrugReplicates", "name": "Drug replicates", "kind": "scatter",
                 "role": "raw replicate markers", "data": {"x": [1.9, 2.1], "y": [18, 22]}},
            ],
        }],
        "scientific_context": {"reference": {"uncertainty": {"representation": "unknown"}}},
    }
    result = build_replacement_bundle(spec, tmp_path)
    raw = (tmp_path / "Raw_Data.csv").read_text(encoding="utf-8-sig")
    summary = (tmp_path / "Summary_Data.csv").read_text(encoding="utf-8-sig")
    assert "Panel,Group,Replicate,Value" in raw
    assert "Main,Control,1,9.0" in raw
    assert "Panel,Group,Center,ErrorPlus,ErrorMinus,ErrorType" in summary
    assert "Main,Control,10.0,2.0,2.0,unknown" in summary
    contract = json.loads((tmp_path / "replacement_contract.json").read_text(encoding="utf-8"))
    assert contract["panels"][0]["mode"] == "categorical_summary_raw"
    assert contract["rules"]["unknown_statistics"] == ["summary_method", "error_method", "p_value_method"]
    assert result["files"]["Raw_Data"].endswith("Raw_Data.csv")


def test_xy_reference_writes_tidy_xy_table(tmp_path):
    spec = {"panels": [{"id": "P1", "series": [{
        "id": "Signal", "name": "Signal", "kind": "line",
        "data": {"x": [1, 2], "y": [3, 4], "y_error": [0.1, 0.2]},
    }]}]}
    build_replacement_bundle(spec, tmp_path)
    xy = (tmp_path / "XY_Data.csv").read_text(encoding="utf-8-sig")
    assert "Panel,Series,Replicate,X,Y,YError,XError" in xy
    assert "P1,Signal,1,1.0,3.0,0.1," in xy


def test_refresh_maps_user_tables_without_inventing_statistics(tmp_path):
    raw_path = tmp_path / "Raw_Data.csv"
    raw_path.write_text(
        "Panel,Group,Replicate,Value\nMain,Control,1,12\nMain,Control,2,14\n",
        encoding="utf-8",
    )
    summary_path = tmp_path / "Summary_Data.csv"
    summary_path.write_text(
        "Panel,Group,Center,ErrorPlus,ErrorMinus,ErrorType\nMain,Control,13,2,2,SEM\n",
        encoding="utf-8",
    )
    spec = {
        "panels": [{
            "id": "Main", "labels": [{"text": "Control"}],
            "series": [
                {"id": "ControlBar", "name": "Control", "kind": "column",
                 "data": {"x": [1], "y": [10], "y_error": [1]}},
                {"id": "ControlReplicates", "name": "Control replicates", "kind": "scatter",
                 "role": "raw replicate markers", "data": {"x": [0.8, 1.2], "y": [9, 11]}},
            ],
        }],
    }
    refreshed = refresh_reference_spec(spec, tmp_path)
    panel = refreshed["panels"][0]
    assert panel["series"][0]["data"]["y"] == [13.0]
    assert panel["series"][0]["data"]["y_error"] == [2.0]
    assert panel["series"][1]["data"]["y"] == [12.0, 14.0]
    assert refreshed["replacement_applied"]["statistics_recomputed"] is False


def test_refresh_keeps_each_summary_on_its_own_category(tmp_path):
    (tmp_path / "Summary_Data.csv").write_text(
        "Panel,Group,Center,ErrorPlus,ErrorMinus,ErrorType\nMain,A,13,2,2,unknown\nMain,B,21,3,3,unknown\n",
        encoding="utf-8",
    )
    spec = {"panels": [{"id": "Main", "labels": [{"text": "A"}, {"text": "B"}], "series": [
        {"id": "ABar", "name": "A", "kind": "column", "data": {"x": [1, 2], "y": [10, 0], "y_error": [1, 0]}},
        {"id": "BBar", "name": "B", "kind": "column", "data": {"x": [1, 2], "y": [0, 20], "y_error": [0, 2]}},
        {"id": "AReplicates", "name": "A replicates", "kind": "scatter", "data": {"x": [1], "y": [10]}},
    ]}]}
    refreshed = refresh_reference_spec(spec, tmp_path)
    assert refreshed["panels"][0]["series"][0]["data"]["y"] == [13.0, 0.0]
    assert refreshed["panels"][0]["series"][1]["data"]["y"] == [0.0, 21.0]
