"""Local spreadsheet ingestion and row search; never executes workbook code."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import sqlite3
import uuid
import zipfile
from datetime import date, datetime, time, timezone
from pathlib import Path

from fastapi import HTTPException
from .storage_layout import safe_name

ROOT = Path(__file__).resolve().parents[2] / "BOL images" / "_AppData"
MAX_BYTES = 50 * 1024 * 1024
MAX_CELLS = 500_000
MAX_COLUMNS = 2048


def spreadsheets_root() -> Path:
    return ROOT.parent / "Spreadsheets" if ROOT.name == "_AppData" else ROOT / "Spreadsheets"


def stored_path(path: Path) -> str:
    root = spreadsheets_root()
    return str(path.relative_to(ROOT)) if root.parent == ROOT else str(Path("..") / path.relative_to(ROOT.parent))


def same_file(first: Path, second: Path) -> bool:
    if not first.is_file() or not second.is_file() or first.stat().st_size != second.stat().st_size:
        return False
    return hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()


def same_tree(first: Path, second: Path) -> bool:
    files = [item for item in first.rglob("*") if item.is_file()]
    return bool(files) and all(same_file(item, second / item.relative_to(first)) for item in files)


def spreadsheet_folder(name: str, file_id: str) -> Path:
    """Readable folder names, with the ID suffix only for duplicate uploads."""
    base = safe_name(Path(name).stem)
    root = spreadsheets_root()
    folder = root / base
    return folder if not folder.exists() else root / f"{base} [{file_id[:8]}]"


def migrate_legacy_spreadsheets() -> int:
    """Organize every older internal upload whenever the app finds one."""
    spreadsheets_root().mkdir(parents=True, exist_ok=True)
    db = connect(); moved = 0
    try:
        # The immediately previous release used a lower-case root but otherwise
        # had the same readable folders. Move it automatically on every scan.
        old_root = ROOT.parent / "spreadsheets"
        new_root = spreadsheets_root()
        if old_root.is_dir() and old_root.resolve() != new_root.resolve():
            for old_folder in list(old_root.iterdir()):
                if not old_folder.is_dir():
                    continue
                target_folder = new_root / old_folder.name
                if not target_folder.exists():
                    shutil.move(str(old_folder), str(target_folder)); moved += 1
                elif same_tree(old_folder, target_folder):
                    shutil.rmtree(old_folder); moved += 1
            try: old_root.rmdir()
            except OSError: pass
        for file in db.execute("SELECT * FROM files").fetchall():
            if str(file["path"]).replace("\\", "/").startswith("../Spreadsheets/"):
                continue
            old_path = ROOT / file["path"]
            if not old_path.is_file():
                # A prior release used BOL images/spreadsheets/{id}/original.ext.
                legacy = ROOT.parent / "spreadsheets" / file["id"] / ("original." + file["kind"])
                old_path = legacy if legacy.is_file() else old_path
            if not old_path.is_file():
                discovered = list(spreadsheets_root().glob("*/" + file["name"]))
                if len(discovered) == 1:
                    db.execute("UPDATE files SET path=? WHERE id=?", (stored_path(discovered[0]), file["id"])); moved += 1
                continue
            folder = spreadsheet_folder(file["name"], file["id"]); folder.mkdir(parents=True, exist_ok=True)
            target = folder / file["name"]
            if target.exists(): target = folder / ("original." + file["kind"])
            shutil.move(str(old_path), str(target))
            metadata = {"id": file["id"], "name": file["name"], "type": file["kind"], "processed_at": file["processed_at"], "warnings": json.loads(file["warnings"])}
            (folder / "spreadsheet-data.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
            db.execute("UPDATE files SET path=? WHERE id=?", (stored_path(target), file["id"])); moved += 1
            try: old_path.parent.rmdir()
            except OSError: pass
        db.commit()
        # Remove an old internal copy only after it matches its organized file.
        for file in db.execute("SELECT id,kind,path FROM files").fetchall():
            organized = (ROOT / file["path"]).resolve()
            for legacy_folder in (ROOT / "uploads" / "spreadsheets" / file["id"], ROOT.parent / "spreadsheets" / file["id"]):
                old = legacy_folder / ("original." + file["kind"])
                if old != organized and same_file(old, organized):
                    shutil.rmtree(legacy_folder)
                    moved += 1
    finally: db.close()
    return moved


def remove_missing_spreadsheet_records() -> int:
    """Keep the gallery index truthful after a user manually removes a folder."""
    db = connect(); removed = 0
    try:
        missing = []
        root = spreadsheets_root().resolve()
        for file in db.execute("SELECT id,path FROM files").fetchall():
            path = (ROOT / file["path"]).resolve()
            within_root = str(path).casefold().startswith(str(root).casefold() + "\\")
            if not within_root or not path.is_file():
                missing.append(file["id"])
        with db:
            for file_id in missing:
                db.execute("DELETE FROM rows WHERE file_id=?", (file_id,))
                db.execute("DELETE FROM sheets WHERE file_id=?", (file_id,))
                db.execute("DELETE FROM files WHERE id=?", (file_id,))
        removed = len(missing)
    finally:
        db.close()
    return removed


def clean_unshown_spreadsheets(keep_ids: set[str]) -> int:
    """Delete spreadsheet folders and indexes that have no View-by-file card."""
    db = connect(); removed = 0; root = spreadsheets_root().resolve()
    try:
        records = db.execute("SELECT id,path FROM files").fetchall()
        with db:
            for file in records:
                if file["id"] in keep_ids:
                    continue
                path = (ROOT / file["path"]).resolve()
                folder = path.parent
                db.execute("DELETE FROM rows WHERE file_id=?", (file["id"],))
                db.execute("DELETE FROM sheets WHERE file_id=?", (file["id"],))
                db.execute("DELETE FROM files WHERE id=?", (file["id"],))
                if folder.parent == root and folder.is_dir():
                    shutil.rmtree(folder)
                removed += 1
        referenced = {(ROOT / row["path"]).resolve().parent for row in db.execute("SELECT path FROM files").fetchall()}
        for folder in root.iterdir() if root.is_dir() else []:
            if folder.is_dir() and folder.resolve() not in referenced:
                shutil.rmtree(folder); removed += 1
    finally:
        db.close()
    return removed


def connect():
    ROOT.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(ROOT / "spreadsheets.db", timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE IF NOT EXISTS files (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
          path TEXT NOT NULL, processed_at TEXT NOT NULL, warnings TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sheets (
          file_id TEXT NOT NULL, idx INTEGER NOT NULL, name TEXT NOT NULL,
          columns INTEGER NOT NULL, PRIMARY KEY(file_id,idx));
        CREATE TABLE IF NOT EXISTS rows (
          file_id TEXT NOT NULL, sheet_idx INTEGER NOT NULL, row_no INTEGER NOT NULL,
          cells TEXT NOT NULL, search_text TEXT NOT NULL,
          PRIMARY KEY(file_id,sheet_idx,row_no));
    ''')
    return db


def column_name(index):
    result = ""
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def display(value, number_format=""):
    if value is None:
        return ""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        if re.fullmatch(r"0{2,}", number_format) and float(value).is_integer():
            return str(int(value)).zfill(len(number_format))
        return str(int(value)) if float(value).is_integer() else str(value)
    return str(value)


def extract(content, suffix):
    """Return (sheet name, row iterator) pairs and extraction caveats."""
    warnings = []
    if suffix == ".csv":
        try:
            text = content.decode("utf-16" if content.startswith((b'\xff\xfe', b'\xfe\xff')) else "utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("cp1252")
            warnings.append("CSV decoded as Windows-1252 because it was not UTF-8.")
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = ([{"column": i, "value": value} for i, value in enumerate(row, 1)]
                for row in csv.reader(io.StringIO(text, newline=""), dialect))
        return [("CSV", rows)], warnings, lambda: None
    if suffix == ".xlsx":
        import openpyxl
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(x.file_size for x in archive.infolist()) > 200 * 1024 * 1024:
                raise ValueError("Uncompressed workbook exceeds 200 MB.")
        formulas = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=False, keep_links=False)
        values = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True, keep_links=False)

        def rows(ws, cached):
            if (ws.max_column or 0) > MAX_COLUMNS or (ws.max_row or 0) * (ws.max_column or 0) > 2_000_000:
                raise ValueError("Worksheet dimensions are too large for the local table viewer.")
            for raw, result in zip(ws.iter_rows(), cached.iter_rows()):
                cells = []
                for col, (cell, cache) in enumerate(zip(raw, result), 1):
                    if cell.value is None:
                        continue
                    formula = str(cell.value) if cell.data_type == "f" else ""
                    val = cache.value if formula else cell.value
                    item = {"column": col, "value": display(val, cell.number_format)}
                    if formula:
                        item["formula"] = formula
                        if val is None:
                            item["value"] = "[Formula result unavailable]"
                            if "Some formulas have no saved result; they were not recalculated." not in warnings:
                                warnings.append("Some formulas have no saved result; they were not recalculated.")
                    cells.append(item)
                yield cells
        return [(ws.title, rows(ws, values[ws.title])) for ws in formulas], warnings, lambda: (formulas.close(), values.close())
    import xlrd
    book = xlrd.open_workbook(file_contents=content, on_demand=True, formatting_info=True)
    warnings.append("XLS displays saved values; formula expressions are not available. No recalculation was performed.")

    def xls_rows(sheet):
        if sheet.ncols > MAX_COLUMNS or sheet.nrows * sheet.ncols > 2_000_000:
            raise ValueError("Worksheet dimensions are too large for the local table viewer.")
        for row in range(sheet.nrows):
            result = []
            for col in range(sheet.ncols):
                cell = sheet.cell(row, col)
                if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                    continue
                value = cell.value
                if cell.ctype == xlrd.XL_CELL_DATE:
                    value = xlrd.xldate_as_datetime(value, book.datemode)
                elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                    value = bool(value)
                elif cell.ctype == xlrd.XL_CELL_ERROR:
                    value = xlrd.error_text_from_code.get(value, "#ERROR!")
                fmt = book.format_map[book.xf_list[cell.xf_index].format_key].format_str
                result.append({"column": col + 1, "value": display(value, fmt)})
            yield result
    return [(s.name, xls_rows(s)) for s in book.sheets()], warnings, book.release_resources


def ingest(name, content, file_id: str | None = None, existing_path: Path | None = None):
    name = name.replace("\\", "/").split("/")[-1]
    suffix = Path(name).suffix.lower()
    if suffix not in {".xls", ".xlsx", ".csv"}:
        raise HTTPException(400, "Choose an XLS, XLSX or CSV file.")
    if not content or len(content) > MAX_BYTES:
        raise HTTPException(413, "Each spreadsheet must contain data and be no larger than 50 MB.")
    file_id = file_id or uuid.uuid4().hex
    spreadsheets_root().mkdir(parents=True, exist_ok=True)
    path = existing_path or (spreadsheet_folder(name, file_id) / name)
    folder = path.parent
    folder.mkdir(parents=True, exist_ok=True)
    if not existing_path:
        path.write_bytes(content)
    db = connect()
    close = lambda: None
    try:
        sheets, warnings, close = extract(content, suffix)
        with db:
            total = 0
            for idx, (title, rows) in enumerate(sheets):
                columns = 0
                for row_no, cells in enumerate(rows, 1):
                    total += len(cells)
                    if total > MAX_CELLS:
                        raise ValueError("Spreadsheet exceeds the 500,000-cell import limit.")
                    if not cells:
                        continue
                    for cell in cells:
                        if cell["column"] > MAX_COLUMNS:
                            raise ValueError("Spreadsheet has too many columns.")
                        cell["address"] = column_name(cell["column"]) + str(row_no)
                        columns = max(columns, cell["column"])
                    search = " ".join(c["value"] + " " + c.get("formula", "") for c in cells).casefold()
                    db.execute("INSERT INTO rows VALUES (?,?,?,?,?)", (file_id, idx, row_no, json.dumps(cells, ensure_ascii=False), search))
                db.execute("INSERT INTO sheets VALUES (?,?,?,?)", (file_id, idx, title, columns))
            db.execute("INSERT INTO files VALUES (?,?,?,?,?,?)", (file_id, name, suffix[1:], stored_path(path), datetime.now(timezone.utc).isoformat(), json.dumps(warnings)))
        (folder / "spreadsheet-data.json").write_text(json.dumps({"id": file_id, "name": name, "type": suffix[1:], "warnings": warnings}, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"id": file_id, "name": name, "cells": total, "warnings": warnings}
    except Exception as error:
        # Retain failed originals, but do not publish a partial index.
        raise HTTPException(400, "Could not read spreadsheet: " + str(error)) from error
    finally:
        close()
        db.close()


def reindex_existing_spreadsheets() -> int:
    """Restore an index from visible spreadsheet folders without copying files."""
    indexed = 0
    for metadata_path in spreadsheets_root().glob("*/spreadsheet-data.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            name, file_id = str(metadata["name"]), str(metadata["id"])
            path = metadata_path.parent / name
            if not re.fullmatch(r"[0-9a-f]{32}", file_id) or not path.is_file():
                continue
            db = connect()
            try:
                exists = db.execute("SELECT 1 FROM files WHERE id=?", (file_id,)).fetchone() is not None
            finally:
                db.close()
            if not exists:
                ingest(name, path.read_bytes(), file_id=file_id, existing_path=path)
                indexed += 1
        except (OSError, KeyError, json.JSONDecodeError, HTTPException):
            continue
    return indexed


def cards(query=""):
    migrate_legacy_spreadsheets()
    reindex_existing_spreadsheets()
    remove_missing_spreadsheet_records()
    db = connect()
    try:
        result = []
        for file in db.execute("SELECT * FROM files ORDER BY processed_at DESC"):
            term = query.strip().casefold()
            hit = db.execute("SELECT r.sheet_idx,r.row_no,r.cells,s.name AS sheet_name FROM rows r JOIN sheets s ON s.file_id=r.file_id AND s.idx=r.sheet_idx WHERE r.file_id=? AND instr(r.search_text,?)>0 ORDER BY r.sheet_idx,r.row_no LIMIT 1", (file["id"], term)).fetchone() if term else None
            if term and term not in file["name"].casefold() and not hit:
                continue
            count = db.execute("SELECT count(*) FROM sheets WHERE file_id=?", (file["id"],)).fetchone()[0]
            preview = ""
            if hit:
                matching = [c["address"] for c in json.loads(hit["cells"]) if term in (c["value"] + " " + c.get("formula", "")).casefold()]
                preview = hit["sheet_name"] + " · Row " + str(hit["row_no"]) + (" · " + ", ".join(matching[:5]) if matching else "")
            result.append({"file_id": file["id"], "file_type": file["kind"], "name": file["name"], "pdf": file["name"], "pdf_folder": "spreadsheet:" + file["id"], "sheet_count": count, "date": file["processed_at"][:10], "processed_at": file["processed_at"], "text": query if hit else "", "trash": False, "page": 0})
            result[-1]["match_preview"] = preview
        return result
    finally:
        db.close()


def file_record(db, file_id):
    row = db.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Spreadsheet not found.")
    return row


def table(file_id, sheet=None, query="", offset=0, limit=100):
    db = connect()
    try:
        file = file_record(db, file_id)
        where, args = "r.file_id=?", [file_id]
        if sheet is not None:
            where += " AND r.sheet_idx=?"
            args.append(sheet)
        if query.strip():
            where += " AND instr(r.search_text,?)>0"
            args.append(query.strip().casefold())
        total = db.execute("SELECT count(*) FROM rows r WHERE " + where, args).fetchone()[0]
        rows = db.execute("SELECT r.*,s.name AS sheet_name FROM rows r JOIN sheets s ON s.file_id=r.file_id AND s.idx=r.sheet_idx WHERE " + where + " ORDER BY r.sheet_idx,r.row_no LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
        sheets = [dict(s) for s in db.execute("SELECT idx,name,columns FROM sheets WHERE file_id=? ORDER BY idx", (file_id,))]
        return {"name": file["name"], "sheets": sheets, "warnings": json.loads(file["warnings"]), "total": total, "offset": offset, "limit": limit, "rows": [{"sheet": r["sheet_name"], "sheet_idx": r["sheet_idx"], "row": r["row_no"], "cells": json.loads(r["cells"])} for r in rows]}
    finally:
        db.close()


def original(file_id):
    db = connect()
    try:
        file = file_record(db, file_id)
        path = (ROOT / file["path"]).resolve()
        if spreadsheets_root().resolve() not in path.parents or not path.is_file():
            raise HTTPException(404, "Original spreadsheet is unavailable.")
        return path, file["name"]
    finally:
        db.close()


def delete_permanently(file_id):
    """Remove one explicitly identified imported original and its search index."""
    if not re.fullmatch(r"[0-9a-f]{32}", file_id):
        raise HTTPException(404, "Spreadsheet not found.")
    db = connect()
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            file = file_record(db, file_id)
            path = (ROOT / file["path"]).resolve()
            base = spreadsheets_root().resolve(); folder = path.parent
            try:
                metadata = json.loads((folder / "spreadsheet-data.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metadata = {}
            if (file["kind"] not in {"xls", "xlsx", "csv"} or base not in folder.parents
                    or path.parent != folder or path.suffix.lower() != "." + file["kind"]
                    or metadata.get("id") != file_id):
                raise HTTPException(400, "Unsafe spreadsheet path; nothing was deleted.")
            for table_name in ("rows", "sheets", "files"):
                key = "id" if table_name == "files" else "file_id"
                db.execute(f"DELETE FROM {table_name} WHERE {key}=?", (file_id,))
            # Never recurse or delete the user's source outside the upload store.
            shutil.rmtree(folder)
        return {"id": file_id, "name": file["name"], "deleted": True}
    except OSError as error:
        raise HTTPException(409, "Could not delete the original file. Close it and try again.") from error
    finally:
        db.close()
