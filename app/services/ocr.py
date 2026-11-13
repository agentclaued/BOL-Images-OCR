import base64
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import httpx
from openai import OpenAI

OCR_PROMPT = """Extract all readable text from this document page exactly as shown.
Preserve headings, labels, numbers, dates, and table rows where possible. Do not invent
missing values. After the transcription, list any unreadable or uncertain content under
the heading `Exceptions:`."""

PROVIDERS = {
    "openai": {"label": "OpenAI", "key_env": "OPENAI_API_KEY", "model_env": "OPENAI_OCR_MODEL", "default_model": "gpt-4.1-mini"},
    "anthropic": {"label": "Anthropic Claude", "key_env": "ANTHROPIC_API_KEY", "model_env": "ANTHROPIC_OCR_MODEL", "default_model": "claude-sonnet-4-5"},
    "gemini": {"label": "Google Gemini", "key_env": "GEMINI_API_KEY", "model_env": "GEMINI_OCR_MODEL", "default_model": "gemini-2.5-flash"},
    "compatible": {"label": "OpenAI-compatible API", "key_env": "COMPATIBLE_API_KEY", "model_env": "COMPATIBLE_OCR_MODEL", "default_model": ""},
    "ocrmypdf": {"label": "OCRmyPDF (local)", "key_env": "", "model_env": "", "default_model": "local"},
    "pymupdf": {"label": "PyMuPDF (local)", "key_env": "", "model_env": "", "default_model": "local"},
    "rapidocr": {"label": "RapidOCR (local)", "key_env": "", "model_env": "", "default_model": "local"},
}


def resolve_provider(provider: str, requested_model: str) -> tuple[str, str, str]:
    if provider not in PROVIDERS:
        raise ValueError("Select a supported OCR provider.")
    settings = PROVIDERS[provider]
    if provider in {"ocrmypdf", "pymupdf", "rapidocr"}:
        return "", "local", settings["label"]
    api_key = os.getenv(settings["key_env"], "").strip()
    model = requested_model.strip() or os.getenv(settings["model_env"], settings["default_model"]).strip()
    if not api_key:
        raise ValueError(f"{settings['key_env']} is not configured in .env.")
    if not model:
        raise ValueError(f"Choose a model or set {settings['model_env']} in .env.")
    if provider == "compatible" and not os.getenv("COMPATIBLE_API_BASE_URL", "").strip():
        raise ValueError("COMPATIBLE_API_BASE_URL is not configured in .env.")
    return api_key, model, settings["label"]


def _image_base64(image_path: Path) -> str:
    return base64.b64encode(image_path.read_bytes()).decode("ascii")


def _openai_response(image_data: str, api_key: str, model: str, base_url: str | None = None) -> str:
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.responses.create(
        model=model,
        input=[{"role": "user", "content": [
            {"type": "input_text", "text": OCR_PROMPT},
            {"type": "input_image", "image_url": f"data:image/png;base64,{image_data}"},
        ]}],
    )
    return response.output_text.strip()


def _anthropic_response(image_data: str, api_key: str, model: str) -> str:
    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        json={"model": model, "max_tokens": 4096, "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_data}},
            {"type": "text", "text": OCR_PROMPT},
        ]}]}, timeout=120,
    )
    response.raise_for_status()
    return "\n".join(part["text"] for part in response.json()["content"] if part.get("type") == "text").strip()


def _gemini_response(image_data: str, api_key: str, model: str) -> str:
    response = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": api_key},
        json={"contents": [{"parts": [
            {"inline_data": {"mime_type": "image/png", "data": image_data}},
            {"text": OCR_PROMPT},
        ]}]}, timeout=120,
    )
    response.raise_for_status()
    parts = response.json()["candidates"][0]["content"]["parts"]
    return "\n".join(part["text"] for part in parts if "text" in part).strip()


def _compatible_response(image_data: str, api_key: str, model: str, base_url: str) -> str:
    """Call the broadly supported OpenAI-compatible Chat Completions vision format."""
    response = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": [{"role": "user", "content": [
            {"type": "text", "text": OCR_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
        ]}]}, timeout=120,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return content if isinstance(content, str) else "\n".join(part.get("text", "") for part in content).strip()


def extract_page_text(image_path: Path, provider: str, model: str) -> str:
    """Extract OCR text with the selected configured AI provider."""
    api_key, resolved_model, _ = resolve_provider(provider, model)
    image_data = _image_base64(image_path)
    if provider == "openai":
        return _openai_response(image_data, api_key, resolved_model)
    if provider == "anthropic":
        return _anthropic_response(image_data, api_key, resolved_model)
    if provider == "gemini":
        return _gemini_response(image_data, api_key, resolved_model)
    return _compatible_response(image_data, api_key, resolved_model, os.getenv("COMPATIBLE_API_BASE_URL", ""))


@lru_cache(maxsize=1)
def _rapidocr_engine():
    try:
        from rapidocr import RapidOCR
    except ImportError as error:
        raise RuntimeError("RapidOCR is not installed. Run: python -m pip install rapidocr onnxruntime") from error
    return RapidOCR()


def extract_rapidocr_text(image_path: Path) -> str:
    """Return local RapidOCR text in the detected reading order."""
    result = _rapidocr_engine()(str(image_path))
    return "\n".join(result.txts or []).strip()


def extract_rapidocr_lines(image) -> list[list]:
    """Return [x0, y0, x1, y1, text] per detected line (pixel coordinates)."""
    result = _rapidocr_engine()(image if isinstance(image, (bytes, bytearray)) else str(image))
    lines: list[list] = []
    if result.boxes is None or result.txts is None:
        return lines
    for box, text in zip(result.boxes, result.txts):
        text = str(text).strip()
        if not text:
            continue
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        lines.append([min(xs), min(ys), max(xs), max(ys), text])
    return lines


def build_searchable_pdf(source_pdf: Path, output_pdf: Path, page_lines: dict[int, list] | None = None, dpi: int = 200) -> None:
    """Write a copy of source_pdf with an invisible RapidOCR text layer.

    page_lines maps page number -> RapidOCR lines already measured at `dpi`.
    Pages not in the map are rendered and OCR'd here. Pages that already have
    embedded text are left untouched. The source PDF is never modified.
    """
    import pymupdf as fitz  # PyMuPDF 1.28+ has no 'fitz' module

    page_lines = page_lines or {}
    scale = 72 / dpi
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    font = fitz.Font("helv")
    with fitz.open(source_pdf) as document:
        for page in document:
            if page.get_text().strip():
                continue
            lines = page_lines.get(page.number + 1)
            if lines is None:
                lines = extract_rapidocr_lines(page.get_pixmap(matrix=matrix, alpha=False).tobytes("png"))
            to_page = page.derotation_matrix
            for x0, y0, x1, y1, text in lines:
                height, width = (y1 - y0) * scale, (x1 - x0) * scale
                size = max(2.0, min(height * 0.85, 72.0))
                natural = font.text_length(text, fontsize=size)
                if natural > width > 0:
                    size = max(1.0, size * width / natural)
                try:
                    page.insert_text(
                        fitz.Point(x0 * scale, y1 * scale - height * 0.2) * to_page,
                        text, fontsize=size, fontname="helv", render_mode=3, rotate=page.rotation,
                    )
                except Exception:
                    continue
        document.save(output_pdf, garbage=3, deflate=True)
