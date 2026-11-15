"""Extracción de contenido de PDF.

Ruta A: PDF con texto seleccionable -> PyMuPDF (conserva tamaño de fuente y negrita,
        que luego sirven para detectar títulos).
Ruta B: PDF escaneado -> Tesseract OCR ejecutado localmente (sin servicios externos).

La decisión se toma página por página: una página con poco texto y mucha imagen se
envía a OCR; una página prácticamente vacía se omite.
"""
from __future__ import annotations

import itertools
import logging
import re
import shutil
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from ..config import Settings
from .text_utils import collapse

log = logging.getLogger("edumap.extractor")

MIN_CHARS_PER_PAGE = 40        # menos que esto: la página no tiene capa de texto útil
MIN_IMAGE_COVERAGE = 0.35      # fracción de la página cubierta por imágenes para considerarla escaneada
MIN_WORDS_TOTAL = 30           # menos palabras que esto: contenido insuficiente

_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "\u00ad": "", "\u200b": ""}
_PAGE_NUMBER = re.compile(r"(?:p[áa]g(?:ina)?\.?\s*)?\d{1,4}(?:\s*(?:/|de)\s*\d{1,4})?", re.IGNORECASE)


class ExtractionError(Exception):
    """Error de extracción con un mensaje apto para mostrarse al usuario."""


class PdfOpenError(ExtractionError):
    pass


class OcrUnavailableError(ExtractionError):
    pass


@dataclass
class Line:
    text: str
    page: int
    size: float
    bold: bool
    block: int
    rel_y: float = 0.5          # posición vertical relativa (0 arriba, 1 abajo)


@dataclass
class Extraction:
    lines: list[Line]
    page_count: int
    method: str                 # "text" | "ocr" | "mixed" | "manual"
    metadata_title: str | None = None
    warnings: list[str] = field(default_factory=list)
    has_style_info: bool = True
    mean_confidence: float | None = None

    @property
    def word_count(self) -> int:
        return sum(len(line.text.split()) for line in self.lines)

    @property
    def uses_ocr(self) -> bool:
        return self.method in ("ocr", "mixed")

    def as_plain_text(self) -> str:
        """Texto legible y editable: bloques separados por línea en blanco y marcas de página."""
        out: list[str] = []
        current_page = None
        current_block = None
        buf: list[str] = []

        def flush() -> None:
            if buf:
                out.append(" ".join(buf))
                out.append("")
                buf.clear()

        for ln in self.lines:
            if ln.page != current_page:
                flush()
                out.append(f"[[Página {ln.page}]]")
                out.append("")
                current_page, current_block = ln.page, None
            if ln.block != current_block:
                flush()
                current_block = ln.block
            buf.append(ln.text)
        flush()
        return "\n".join(out).strip()


# --------------------------------------------------------------------------- apertura
def open_pdf(path: Path) -> pymupdf.Document:
    try:
        doc = pymupdf.open(path)
    except Exception as exc:  # archivo corrupto o formato no soportado
        raise PdfOpenError("No se pudo abrir el archivo: está dañado o no es un PDF válido.") from exc
    if doc.needs_pass or doc.is_encrypted:
        doc.close()
        raise PdfOpenError("El PDF está protegido con contraseña. Quita la protección y vuelve a subirlo.")
    if doc.page_count == 0:
        doc.close()
        raise PdfOpenError("El PDF no contiene páginas.")
    return doc


def inspect_pdf(path: Path) -> int:
    """Valida que el PDF se pueda abrir y devuelve su número de páginas."""
    doc = open_pdf(path)
    try:
        return doc.page_count
    finally:
        doc.close()


# --------------------------------------------------------------------------- ruta A
def _clean(text: str) -> str:
    for src, dst in _LIGATURES.items():
        text = text.replace(src, dst)
    # Viñetas de fuentes Symbol/Wingdings llegan como caracteres de uso privado
    text = re.sub(r"^[\uf000-\uf0ff]\s*", "• ", text)
    return collapse(text)


def _is_bold(span: dict) -> bool:
    return bool(span["flags"] & 16) or any(
        k in span["font"].lower() for k in ("bold", "black", "heavy", "semibold", "demi")
    )


def _extract_page_text(page: pymupdf.Page, page_no: int, blocks: itertools.count) -> list[Line]:
    height = page.rect.height or 1.0
    lines: list[Line] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        block_id = next(blocks)
        for raw in block["lines"]:
            spans = [s for s in raw["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = _clean("".join(s["text"] for s in raw["spans"]))
            if not text:
                continue
            weights = Counter()
            for s in spans:
                weights[round(s["size"], 1)] += len(s["text"].strip())
            size = weights.most_common(1)[0][0]
            bold_chars = sum(len(s["text"].strip()) for s in spans if _is_bold(s))
            total_chars = sum(len(s["text"].strip()) for s in spans)
            y0, y1 = raw["bbox"][1], raw["bbox"][3]
            lines.append(
                Line(text=text, page=page_no, size=size, bold=bold_chars >= 0.6 * total_chars,
                     block=block_id, rel_y=((y0 + y1) / 2) / height)
            )
    return lines


def _image_coverage(page: pymupdf.Page) -> float:
    area = page.rect.width * page.rect.height or 1.0
    covered = 0.0
    for info in page.get_image_info():
        rect = pymupdf.Rect(info["bbox"]) & page.rect
        if not rect.is_empty:
            covered += rect.width * rect.height
    return min(1.0, covered / area)


def _strip_repeated_margins(pages: dict[int, list[Line]], page_count: int) -> None:
    """Quita encabezados/pies repetidos y números de página (solo en márgenes)."""
    def in_margin(ln: Line) -> bool:
        return ln.rel_y < 0.09 or ln.rel_y > 0.91

    counts: Counter[str] = Counter()
    for lines in pages.values():
        seen = {re.sub(r"\d+", "#", ln.text.lower()) for ln in lines if in_margin(ln)}
        counts.update(seen)
    min_repeat = max(3, int(0.5 * page_count))
    repeated = {k for k, v in counts.items() if v >= min_repeat}
    for page_no, lines in pages.items():
        pages[page_no] = [
            ln for ln in lines
            if not (in_margin(ln) and (
                re.sub(r"\d+", "#", ln.text.lower()) in repeated or _PAGE_NUMBER.fullmatch(ln.text)
            ))
        ]


# --------------------------------------------------------------------------- ruta B (OCR)
def _configure_tesseract(settings: Settings):
    import pytesseract

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    return pytesseract


def ocr_available(settings: Settings) -> bool:
    try:
        pytesseract = _configure_tesseract(settings)
        if not settings.tesseract_cmd and shutil.which("tesseract") is None:
            return False
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def ocr_languages_available(settings: Settings) -> list[str]:
    try:
        pytesseract = _configure_tesseract(settings)
        return sorted(l for l in pytesseract.get_languages(config="") if l != "osd")
    except Exception:
        return []


def _choose_ocr_language(settings: Settings) -> tuple[str, list[str]]:
    available = ocr_languages_available(settings)
    wanted = [l for l in settings.ocr_languages if l in available]
    warnings: list[str] = []
    if "spa" in settings.ocr_languages and "spa" not in available:
        warnings.append(
            "Tesseract no tiene el idioma español (spa) instalado; se usó el inglés y es probable "
            "que haya errores con acentos y eñes. Instala el paquete de idioma «spa»."
        )
    if not wanted:
        wanted = ["eng"] if "eng" in available else available[:1]
    if not wanted:
        raise OcrUnavailableError("Tesseract está instalado pero no tiene ningún idioma disponible.")
    return "+".join(wanted), warnings


def _ocr_page(page: pymupdf.Page, page_no: int, lang: str, dpi: int,
              blocks: itertools.count, pytesseract) -> tuple[list[Line], list[float]]:
    from PIL import Image

    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    data = pytesseract.image_to_data(image, lang=lang, config="--psm 3",
                                     output_type=pytesseract.Output.DICT)
    grouped: dict[tuple[int, int, int], list[int]] = {}
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        grouped.setdefault(key, []).append(i)

    block_ids: dict[tuple[int, int], int] = {}
    lines: list[Line] = []
    confidences: list[float] = []
    for key in sorted(grouped):
        idx = grouped[key]
        text = _clean(" ".join(data["text"][i] for i in idx))
        if not text:
            continue
        heights = [data["height"][i] for i in idx]
        top = min(data["top"][i] for i in idx)
        bid = block_ids.setdefault(key[:2], next(blocks))
        lines.append(Line(text=text, page=page_no, size=statistics.median(heights) / zoom,
                          bold=False, block=bid, rel_y=top / max(pix.height, 1)))
        for i in idx:
            conf = float(data["conf"][i])
            if conf >= 0:
                confidences.append(conf)
    return lines, confidences


# --------------------------------------------------------------------------- principal
def extract_document(path: Path, settings: Settings) -> Extraction:
    doc = open_pdf(path)
    try:
        if doc.page_count > settings.max_pages:
            raise ExtractionError(
                f"El PDF tiene {doc.page_count} páginas y el límite es {settings.max_pages}."
            )
        meta_title = collapse((doc.metadata or {}).get("title") or "") or None
        if meta_title and (re.match(r"(?i)^(microsoft word|untitled|sin t[ií]tulo|documento\d*)", meta_title)
                           or re.search(r"(?i)\.(docx?|pdf|odt|tex|pptx?)$", meta_title)):
            meta_title = None

        counter = itertools.count()
        text_pages: dict[int, list[Line]] = {}
        ocr_candidates: list[int] = []
        for idx, page in enumerate(doc, start=1):
            lines = _extract_page_text(page, idx, counter)
            chars = sum(len(ln.text.replace(" ", "")) for ln in lines)
            if chars >= MIN_CHARS_PER_PAGE:
                text_pages[idx] = lines
            elif _image_coverage(page) >= MIN_IMAGE_COVERAGE:
                ocr_candidates.append(idx)
        if not text_pages and not ocr_candidates:
            # Sin capa de texto ni imágenes (p. ej. texto convertido a trazos): se intenta OCR
            ocr_candidates = list(range(1, doc.page_count + 1))

        warnings: list[str] = []
        ocr_pages: dict[int, list[Line]] = {}
        confidences: list[float] = []
        if ocr_candidates:
            if not ocr_available(settings):
                if not text_pages:
                    raise OcrUnavailableError(
                        "Este PDF parece escaneado (no tiene texto seleccionable) y Tesseract OCR no está "
                        "disponible en este equipo. Instala Tesseract (ver README) o sube un PDF con texto."
                    )
                warnings.append(
                    f"{len(ocr_candidates)} página(s) parecen imágenes y se omitieron porque "
                    "Tesseract OCR no está instalado."
                )
            else:
                if len(ocr_candidates) > settings.max_ocr_pages:
                    warnings.append(
                        f"Solo se procesaron con OCR las primeras {settings.max_ocr_pages} páginas "
                        f"de {len(ocr_candidates)} que lo necesitaban."
                    )
                    ocr_candidates = ocr_candidates[: settings.max_ocr_pages]
                lang, lang_warnings = _choose_ocr_language(settings)
                warnings.extend(lang_warnings)
                pytesseract = _configure_tesseract(settings)
                for page_no in ocr_candidates:
                    try:
                        lines, conf = _ocr_page(doc[page_no - 1], page_no, lang, settings.ocr_dpi,
                                                counter, pytesseract)
                    except Exception as exc:
                        log.warning("OCR falló en la página %s: %s", page_no, exc)
                        warnings.append(f"El OCR falló en la página {page_no}.")
                        continue
                    ocr_pages[page_no] = lines
                    confidences.extend(conf)

        _strip_repeated_margins(text_pages, doc.page_count)

        merged = {**text_pages, **ocr_pages}
        ordered = [ln for p in sorted(merged) for ln in merged[p]]
        method = "mixed" if text_pages and ocr_pages else "ocr" if ocr_pages else "text"
        mean_conf = statistics.fmean(confidences) if confidences else None
        return Extraction(lines=ordered, page_count=doc.page_count, method=method,
                          metadata_title=meta_title, warnings=warnings,
                          has_style_info=True, mean_confidence=mean_conf)
    finally:
        doc.close()


# --------------------------------------------------------------------------- texto manual
_PAGE_MARK = re.compile(r"^\[\[P[áa]gina\s+(\d+)\]\]\s*$", re.IGNORECASE)


def extraction_from_text(text: str, page_count: int = 1) -> Extraction:
    """Construye una extracción a partir de texto revisado a mano (sin información de fuente)."""
    lines: list[Line] = []
    page = 1
    block = 0
    in_block = False
    for raw in text.splitlines():
        mark = _PAGE_MARK.match(raw.strip())
        if mark:
            page = max(1, int(mark.group(1)))
            in_block = False
            continue
        line = _clean(raw)
        if not line:
            in_block = False
            continue
        if not in_block:
            block += 1
            in_block = True
        lines.append(Line(text=line, page=page, size=10.0, bold=False, block=block))
    return Extraction(lines=lines, page_count=max(page_count, page), method="manual",
                      has_style_info=False)
