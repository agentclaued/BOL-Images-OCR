"""Filename-based on-disk layout and one-time legacy gallery migration."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "BOL images"
PDFS = ROOT / "PDFs"
IMAGES = ROOT / "Images"
SPREADSHEETS = ROOT / "Spreadsheets"


def safe_name(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value)).strip(" .") or "Unknown"


def unique_folder(root: Path, base: str, source_hash: str = "") -> Path:
    candidate = root / base
    if not candidate.exists():
        return candidate
    if source_hash and (candidate / "ocr-results.json").is_file():
        try:
            if json.loads((candidate / "ocr-results.json").read_text(encoding="utf-8")).get("source_sha256") == source_hash:
                return candidate
        except (OSError, json.JSONDecodeError):
            pass
    suffix = (" [" + source_hash[:12] + "]") if source_hash else ""
    number = 2
    while (root / f"{base}{suffix} {number}").exists():
        number += 1
    return root / f"{base}{suffix} {number}"


def migrate_legacy_gallery() -> int:
    """Move legacy PDF page JPGs into their own PDF folder."""
    PDFS.mkdir(parents=True, exist_ok=True); IMAGES.mkdir(parents=True, exist_ok=True); SPREADSHEETS.mkdir(parents=True, exist_ok=True)
    moved = 0
    for manifest_path in list(ROOT.rglob("ocr-results.json")):
        if PDFS in manifest_path.parents:
            continue
        old = manifest_path.parent
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source = Path(str(manifest.get("source_pdf", ""))).name
        folder = unique_folder(PDFS, safe_name(Path(source).stem or old.name), str(manifest.get("source_sha256", "")))
        images = folder / "Images"
        folder.mkdir(parents=True, exist_ok=True); images.mkdir(parents=True, exist_ok=True)
        for filename in {source, str(manifest.get("searchable_pdf") or "")}:
            item = old / Path(filename).name
            if item.is_file() and not (folder / item.name).exists(): shutil.move(str(item), str(folder / item.name))
        for page in manifest.get("pages", []):
            name = Path(str(page.get("image", ""))).name
            for origin, destination in ((old / name, images / name), (old / "Trash" / name, images / "Trash" / name)):
                if origin.is_file() and not destination.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(origin), str(destination))
        manifest.pop("company", None)
        for page in manifest.get("pages", []): page.pop("detected_company", None)
        manifest["images_folder"] = images.relative_to(ROOT).as_posix()
        (folder / "ocr-results.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest_path.unlink()
        try:
            (old / "Trash").rmdir(); old.rmdir()
        except OSError:
            pass
        moved += 1
    # Previous filename-layout builds still placed page images in the top-level
    # Images folder. Upgrade them each time they are found; that root is now
    # reserved only for files uploaded directly as images.
    for manifest_path in list(PDFS.rglob("ocr-results.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        images = manifest_path.parent / "Images"
        previous = ROOT / str(manifest.get("images_folder", ""))
        if previous.resolve() != images.resolve() and previous.is_dir():
            images.mkdir(exist_ok=True)
            for item in previous.iterdir():
                destination = images / item.name
                if not destination.exists(): shutil.move(str(item), str(destination))
            try: previous.rmdir()
            except OSError: pass
            moved += 1
        if manifest.get("images_folder") != images.relative_to(ROOT).as_posix():
            manifest["images_folder"] = images.relative_to(ROOT).as_posix()
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return moved
