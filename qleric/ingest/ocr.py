"""Tesseract OCR fallback for imageless pages. System binary via subprocess."""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time

logger = logging.getLogger(__name__)

_OCR_DPI = 300.0
_OCR_MAX_SIDE = 3300.0  # px cap on the rendered long edge (memory guard)
_OCR_TIMEOUT = 30  # seconds per page
_OCR_MIN_WORDS = 5
_OCR_MIN_CONF = 30.0
_OCR_MIN_MEAN = 40.0
_TESSERACT = None  # cached version string, False when the binary is missing


def _set_unavailable() -> None:
    """Mark the tesseract binary missing without touching other cache states."""
    global _TESSERACT
    _TESSERACT = False


def _tesseract_version():
    """Tesseract version string, or None when the binary is unavailable."""
    global _TESSERACT
    if _TESSERACT is None:
        try:
            p = subprocess.run(["tesseract", "--version"], capture_output=True,
                               timeout=10, text=True)
            _TESSERACT = (p.stdout or "").splitlines()[0] if p.returncode == 0 else False
        except Exception:
            _TESSERACT = False
    return _TESSERACT or None


def _tsv_text(tsv: str) -> tuple[str, float, int]:
    """Parse tesseract TSV (level 5 = word) into lines; returns (text, mean_conf, n)."""
    lines, cur, key, confs = [], [], None, []
    for row in (tsv or "").splitlines()[1:]:  # skip the header
        parts = row.split("\t")
        if len(parts) < 12 or parts[0] != "5":
            continue
        try:
            conf = float(parts[10])
        except ValueError:
            continue
        word = parts[11].strip()
        if not word:
            continue
        k = (parts[2], parts[3], parts[4])
        if k != key:
            if cur:
                lines.append(" ".join(cur))
            cur, key = [], k
        if conf >= _OCR_MIN_CONF:
            cur.append(word)
            confs.append(conf)
    if cur:
        lines.append(" ".join(cur))
    mean = sum(confs) / len(confs) if confs else 0.0
    return "\n".join(lines), mean, len(confs)


def _ocr_page(page, lang: str = "eng") -> tuple[str, str, float]:
    """OCR one imageless page. Returns (text, status, ms); text "" on any failure.

    Statuses: ok, empty (below the acceptance floor), failed (render/run/parse),
    unavailable (no tesseract binary). Scanned two-column reorder is parked:
    OCR text joins single-column. `lang` is a caller-provided tesseract code;
    env/config reads belong at the application edge, never in here.
    """
    import fitz

    if _tesseract_version() is None:
        return "", "unavailable", 0.0
    try:
        rect = page.rect
        zoom = min(_OCR_DPI / 72.0,
                   _OCR_MAX_SIDE / max(rect.width, rect.height, 1))
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY)
        png = pix.tobytes("png")
        del pix
    except Exception as e:
        logger.debug("ocr render failed: %s", e)
        return "", "failed", 0.0
    t0 = time.perf_counter()
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png)
            path = f.name
        try:
            p = subprocess.run(["tesseract", path, "stdout", "-l", lang, "tsv"],
                               capture_output=True, timeout=_OCR_TIMEOUT)
        finally:
            os.unlink(path)
    except FileNotFoundError:
        _set_unavailable()
        return "", "unavailable", 0.0
    except Exception as e:
        logger.debug("ocr run failed: %s", e)
        return "", "failed", 0.0
    ms = (time.perf_counter() - t0) * 1000
    if p.returncode != 0:
        return "", "failed", ms
    try:
        text, mean, n = _tsv_text(p.stdout.decode("utf-8", "replace"))
    except Exception:
        return "", "failed", ms
    if n < _OCR_MIN_WORDS or mean < _OCR_MIN_MEAN:
        return "", "empty", ms
    return text, "ok", ms
