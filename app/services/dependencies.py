"""Checks and installation helpers for local OCR prerequisites."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


TESSERACT_LOCATIONS = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)


def find_tesseract() -> Path | None:
    """Find Tesseract and make it available to the current server process."""
    discovered = shutil.which("tesseract") or shutil.which("tesseract.exe")
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    per_user_location = (
        Path(local_app_data) / "Programs" / "Tesseract-OCR" / "tesseract.exe"
        if local_app_data
        else None
    )
    candidates = ([Path(discovered)] if discovered else []) + list(TESSERACT_LOCATIONS)
    if per_user_location:
        candidates.append(per_user_location)
    for candidate in candidates:
        if candidate.is_file():
            folder = str(candidate.parent)
            if folder.casefold() not in os.environ.get("PATH", "").casefold():
                os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
            return candidate
    return None


def ensure_tesseract() -> tuple[bool, str]:
    """Install Tesseract through an available Windows package manager if needed."""
    executable = find_tesseract()
    if executable:
        return True, f"Tesseract available: {executable}"

    installers = (
        (
            "winget",
            [
                "winget",
                "install",
                "--id",
                "UB-Mannheim.TesseractOCR",
                "--exact",
                "--silent",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
        ),
        ("choco", ["choco", "install", "tesseract", "-y", "--no-progress"]),
    )
    for manager, command in installers:
        if not shutil.which(manager):
            continue
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            return False, f"{manager} could not install Tesseract: {error}"
        executable = find_tesseract()
        if result.returncode == 0 and executable:
            return True, f"Tesseract installed with {manager}: {executable}"
        detail = (result.stderr or result.stdout).strip().splitlines()
        return False, f"{manager} could not install Tesseract: {detail[-1] if detail else 'unknown error'}"

    return False, "Tesseract is missing and neither winget nor Chocolatey is installed."
