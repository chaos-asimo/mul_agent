# -*- coding: utf-8 -*-
"""Excel 文本提取（不依赖 pandas）。

- .xlsx/.xlsm：openpyxl（纯 Python，部署包体小）
- 旧版 .xls：xlrd

输出按工作表分节，每行以 " | " 连接，便于模型对齐表头、逐行比对字段。
"""
import os
from datetime import date, datetime, time


def _fmt(value) -> str:
    """单元格值转文本：日期时间可读化，整数值浮点去掉 .0。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.hour or value.minute or value.second:
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _rows_to_text(rows, sheet_title: str = "") -> str:
    lines = []
    for row in rows:
        cells = [_fmt(v) for v in row]
        while cells and not cells[-1]:
            cells.pop()
        if not any(cells):
            continue
        lines.append(" | ".join(cells))
    if not lines:
        return ""
    header = f"# 工作表：{sheet_title}\n" if sheet_title else ""
    return header + "\n".join(lines)


def _read_xlsx(path: str) -> str:
    from openpyxl import load_workbook

    # data_only=True：取公式的缓存计算结果，避免把 "=SUM(A1:A5)" 原样交给模型
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        blocks = [_rows_to_text(ws.iter_rows(values_only=True), ws.title) for ws in wb.worksheets]
    finally:
        wb.close()
    return "\n\n".join([b for b in blocks if b])


def _read_xls(path: str) -> str:
    import xlrd

    book = xlrd.open_workbook(path)
    blocks = []
    for sheet in book.sheets():
        rows = [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]
        blocks.append(_rows_to_text(rows, sheet.name))
    return "\n\n".join([b for b in blocks if b])


def read_excel_text(file_path: str) -> str:
    """读取 Excel 全部工作表为纯文本。依赖缺失时抛出 ImportError。"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".xls":
        return _read_xls(file_path)
    return _read_xlsx(file_path)
