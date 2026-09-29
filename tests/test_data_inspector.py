import pandas as pd
from pathlib import Path

from mcp_server.data_inspector import inspect_dataset, load_tables


def test_inspect_csv_detects_columns_and_candidates(workspace_tmp: Path):
    path = workspace_tmp / "experiment.csv"
    path.write_text("Group,Rep1,Rep2,Rep3\nA,1,2,3\nB,4,5,6\n", encoding="utf-8")

    result = inspect_dataset(path)

    assert result["supported"] is True
    assert result["tables"][0]["row_count"] == 2
    assert result["tables"][0]["columns"][0]["name"] == "Group"
    assert any(candidate["data_model"] == "long_grouped" for candidate in result["tables"][0]["candidate_models"])


def test_load_xlsx_preserves_sheet_names(workspace_tmp: Path):
    path = workspace_tmp / "book.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"Time": [0, 1], "Signal": [2.0, 4.0]}).to_excel(writer, sheet_name="Signal", index=False)

    tables = load_tables(path)

    assert list(tables) == ["Signal"]
    assert list(tables["Signal"].columns) == ["Time", "Signal"]
