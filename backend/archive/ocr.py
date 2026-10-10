"""Text acquisition for archive documents. OCR is optional; if unavailable or unreadable the document is routed to manual review."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ALLOWED = {".pdf", ".txt", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".docx", ".csv", ".xlsx"}


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def available_ocr_languages() -> list[str]:
    if not tesseract_available():
        return []
    try:
        out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10)
        return [l.strip() for l in (out.stdout + out.stderr).splitlines()[1:] if l.strip() and not l.startswith("List")]
    except Exception:
        return []


def _ocr_image(path: Path, langs: str) -> tuple[str, float | None]:
    import pytesseract
    from PIL import Image
    avail = available_ocr_languages()
    use = "+".join([l for l in langs.split("+") if l in avail]) or ("eng" if "eng" in avail else None)
    if not use:
        return "", None
    img = Image.open(path)
    data = pytesseract.image_to_data(img, lang=use, output_type=pytesseract.Output.DICT)
    confs = [float(c) for c in data["conf"] if str(c) not in ("-1", "")]
    text = pytesseract.image_to_string(img, lang=use)
    return text, (sum(confs) / len(confs) / 100.0) if confs else None


def extract_pages(path: Path, langs: str = "rus+aze+eng") -> dict:
    """Return {pages: [text...], text_source: text|ocr|none, ocr_confidence, note}."""
    ext = path.suffix.lower()
    if ext == ".txt":
        return {"pages": [path.read_text(encoding="utf-8", errors="replace")], "text_source": "text", "ocr_confidence": None, "note": ""}
    if ext == ".pdf":
        pages = []
        try:
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                for p in pdf.pages:
                    pages.append(p.extract_text() or "")
        except Exception as e:
            return {"pages": [], "text_source": "none", "ocr_confidence": None, "note": f"PDF could not be opened: {e}"}
        if sum(len(p.strip()) for p in pages) > 40:
            return {"pages": pages, "text_source": "text", "ocr_confidence": None, "note": ""}
        # scanned PDF → rasterise and OCR
        if not tesseract_available() or shutil.which("pdftoppm") is None:
            return {"pages": pages, "text_source": "none", "ocr_confidence": None, "note": "Scanned PDF and no OCR engine available: routed to manual review."}
        try:
            tmp = path.parent / (path.stem + "_ocr")
            tmp.mkdir(exist_ok=True)
            subprocess.run(["pdftoppm", "-r", "200", "-png", str(path), str(tmp / "p")], check=True, timeout=120)
            texts, confs = [], []
            for img in sorted(tmp.glob("p*.png")):
                t, c = _ocr_image(img, langs)
                texts.append(t)
                if c is not None:
                    confs.append(c)
            conf = sum(confs) / len(confs) if confs else None
            note = "" if (conf or 0) >= 0.6 else "Low OCR confidence: routed to manual review."
            return {"pages": texts, "text_source": "ocr", "ocr_confidence": conf, "note": note}
        except Exception as e:
            return {"pages": pages, "text_source": "none", "ocr_confidence": None, "note": f"OCR failed: {e}"}
    if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        if not tesseract_available():
            return {"pages": [], "text_source": "none", "ocr_confidence": None, "note": "No OCR engine available: routed to manual review."}
        try:
            t, c = _ocr_image(path, langs)
            note = "" if (c or 0) >= 0.6 else "Low OCR confidence: routed to manual review."
            missing = [l for l in langs.split("+") if l not in available_ocr_languages()]
            if missing:
                note += f" OCR language packs not installed: {', '.join(missing)}."
            return {"pages": [t], "text_source": "ocr", "ocr_confidence": c, "note": note.strip()}
        except Exception as e:
            return {"pages": [], "text_source": "none", "ocr_confidence": None, "note": f"OCR failed: {e}"}
    if ext == ".docx":
        try:
            import zipfile, re
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
            text = re.sub(r"</w:p>", "\n", xml)
            text = re.sub(r"<[^>]+>", "", text)
            return {"pages": [text], "text_source": "text", "ocr_confidence": None, "note": ""}
        except Exception as e:
            return {"pages": [], "text_source": "none", "ocr_confidence": None, "note": f"DOCX could not be read: {e}"}
    if ext in (".csv", ".xlsx"):
        return {"pages": [], "text_source": "none", "ocr_confidence": None, "note": "Tabular files belong in the Data Hub import wizard, not the archive."}
    return {"pages": [], "text_source": "none", "ocr_confidence": None, "note": "Unsupported file type."}
