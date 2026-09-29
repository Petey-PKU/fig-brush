from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from mcp_server.data_inspector import load_tables
from mcp_server.paths import InputValidationError


def choose_table(data_path: str | Path, table_name: str | None = None) -> pd.DataFrame:
    tables = load_tables(data_path)
    if table_name:
        if table_name not in tables:
            raise InputValidationError(
                f"Table {table_name!r} was not found. Available tables: {', '.join(tables)}"
            )
        return tables[table_name]
    if not tables:
        raise InputValidationError("The data file contains no tables.")
    return next(iter(tables.values()))


def add_dataframe(op: Any, frame: pd.DataFrame, name: str = "Source Data", book: Any | None = None) -> Any:
    """Add ``frame`` as a worksheet, reusing ``book`` when supplied.

    Origin's ``project.new_sheet('w')`` creates a new workbook, which is a
    surprising default for a reference template with many plotted series.
    Reusing the parent WBook keeps all replaceable values for one reference
    image together while preserving one worksheet per series/role.
    """
    new_sheet = getattr(op, "new_sheet", None)
    if book is None and not callable(new_sheet):
        raise RuntimeError("originpro does not expose project.new_sheet().")
    if book is None:
        # OriginSession.new() starts with an empty Book1. Reuse that first
        # sheet when it is genuinely blank so a reference template does not
        # ship with an extra empty workbook beside its data book.
        worksheet = None
        find_book = getattr(op, "find_book", None)
        if callable(find_book):
            try:
                candidate = find_book("w", 0)
                sheets = list(candidate) if candidate is not None else []
                if len(sheets) == 1 and getattr(sheets[0], "rows", 0) == 0:
                    worksheet = sheets[0]
                    try:
                        worksheet.name = name
                    except Exception:
                        pass
            except Exception:
                worksheet = None
        if worksheet is None:
            worksheet = new_sheet("w", name)
    else:
        add_sheet = getattr(book, "add_sheet", None)
        if not callable(add_sheet):
            raise RuntimeError("Origin workbook does not expose add_sheet().")
        worksheet = add_sheet(name)
    from_df = getattr(worksheet, "from_df", None)
    if not callable(from_df):
        raise RuntimeError("Origin worksheet does not expose from_df().")
    from_df(frame)
    for index, column in enumerate(frame.columns):
        set_label = getattr(worksheet, "set_label", None)
        if callable(set_label):
            try:
                set_label(index, str(column))
            except Exception:
                # Column names are already imported by from_df. This is only a
                # compatibility enhancement for older originpro builds.
                pass
    return worksheet


def sheet_range(worksheet: Any) -> str:
    lt_range = getattr(worksheet, "lt_range", None)
    if not callable(lt_range):
        raise RuntimeError("Origin worksheet does not expose lt_range().")
    return str(lt_range())
