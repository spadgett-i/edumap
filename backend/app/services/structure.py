"""Identificación de la estructura del documento con reglas deterministas.

Entrada: líneas con tamaño/negrita (o texto plano). Salida: árbol de secciones con
párrafos y elementos de lista. Señales usadas para los títulos:
  * tamaño de fuente mayor que el cuerpo del texto,
  * negrita en líneas cortas sin punto final,
  * numeración jerárquica (1., 2.1, 2.1.3),
  * en texto plano: líneas en MAYÚSCULAS o líneas cortas seguidas de un párrafo largo.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .pdf_extractor import Extraction, Line
from .text_utils import clean_label

HEADING_SIZE_RATIO_TEXT = 1.12   # PDF con texto: tamaño mínimo respecto al cuerpo
HEADING_SIZE_RATIO_OCR = 1.35    # OCR: la altura de línea es ruidosa, se exige más diferencia
MAX_HEADING_LEVEL = 6

_BULLET = re.compile(r"^(?P<mark>[•●▪◦‣∙·*]|[-–—](?=\s))\s*(?P<body>\S.*)$")
_ENUM = re.compile(r"^(?P<mark>\d{1,3}|[a-zA-Z])[.)]\s+(?P<body>\S.*)$")
_NUM_HEAD = re.compile(r"^(?P<num>\d+(?:\.\d+){0,4})[.)]?\s+(?P<body>\S.*)$")
_BULLET_ONLY = re.compile(r"^[•●▪◦‣∙·*\-–—]$")
_TERMINAL = (".", "!", "?", ";", ",", "…")


@dataclass
class Block:
    kind: str                   # "paragraph" | "list_item"
    text: str
    page: int


@dataclass
class Section:
    title: str
    raw_title: str
    level: int
    page: int
    blocks: list[Block] = field(default_factory=list)
    children: list["Section"] = field(default_factory=list)


@dataclass
class DocumentStructure:
    title: str
    title_page: int
    title_source: str           # "document" | "metadata" | "filename"
    preamble: list[Block]
    sections: list[Section]
    heading_count: int
    page_count: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Unit:
    text: str
    page: int
    size: float
    block: int
    bold_chars: int = 0
    chars: int = 1
    lines: int = 1

    @property
    def bold(self) -> bool:
        return self.bold_chars >= 0.6 * self.chars


def list_marker(text: str) -> tuple[str, str] | None:
    m = _BULLET.match(text)
    if m:
        return m.group("mark"), m.group("body")
    m = _ENUM.match(text)
    if m:
        return m.group("mark"), m.group("body")
    return None


# --------------------------------------------------------------------------- unidades
_TOC_LINE = re.compile(r"^.{3,}?[\s.…·]+\d{1,3}$")
_ONLY_NUMBER = re.compile(r"^\d{1,3}$")
_CAPTION = re.compile(r"^(?:figura|fig\.|tabla|gr[aá]fic[ao]|cuadro)\s*\d+", re.IGNORECASE)


def _drop_toc_lines(lines: list[Line]) -> tuple[list[Line], list[int]]:
    """Quita las tablas de contenido: líneas «título … número» o títulos cuyo número de página
    quedó en una línea aparte (tabulación a la derecha)."""
    by_page: dict[int, list[Line]] = defaultdict(list)
    for ln in lines:
        by_page[ln.page].append(ln)

    def is_hit(l: Line) -> bool:
        return bool(_TOC_LINE.match(l.text) or _ONLY_NUMBER.match(l.text))

    toc_pages = [
        page for page, ls in by_page.items()
        if sum(map(is_hit, ls)) >= 5 and sum(map(is_hit, ls)) >= 0.25 * len(ls)
    ]
    if not toc_pages:
        return lines, []
    drop: set[int] = set()
    for page in toc_pages:
        ls = by_page[page]
        for i, l in enumerate(ls):
            if _TOC_LINE.match(l.text):
                drop.add(id(l))
            elif _ONLY_NUMBER.match(l.text):
                drop.add(id(l))
                if i > 0 and not _ONLY_NUMBER.match(ls[i - 1].text):
                    drop.add(id(ls[i - 1]))
    return [l for l in lines if id(l) not in drop], sorted(toc_pages)


def _build_units(lines: list[Line]) -> list[_Unit]:
    units: list[_Unit] = []
    pending = ""
    for ln in lines:
        text = ln.text
        if _BULLET_ONLY.match(text):
            pending = text
            continue
        if pending:
            text, pending = f"{pending} {text}", ""
        starts_item = list_marker(text) is not None
        prev = units[-1] if units else None
        chars = len(text)
        bold_chars = chars if ln.bold else 0
        # Un título corto en negrita seguido de texto normal en el mismo bloque se separa;
        # un párrafo cuyas primeras palabras van en negrita («Título: …») se mantiene unido.
        heading_like_prev = bool(prev) and prev.bold and prev.lines == 1 and len(prev.text.split()) <= 8 \
            and not prev.text.endswith(_TERMINAL)
        split_on_bold = bool(prev) and ln.bold != prev.bold and heading_like_prev
        if (prev and not starts_item and prev.block == ln.block
                and abs(prev.size - ln.size) <= 0.6 and not split_on_bold):
            if prev.text.endswith("-") and text[:1].islower():
                prev.text = prev.text[:-1] + text
            else:
                prev.text = f"{prev.text} {text}"
            prev.lines += 1
            prev.chars += chars
            prev.bold_chars += bold_chars
        else:
            units.append(_Unit(text, ln.page, ln.size, ln.block, bold_chars, chars))
    return units


def _merge_across_pages(units: list[_Unit]) -> list[_Unit]:
    """Une un párrafo cortado por un salto de página (termina sin punto y sigue en minúscula)."""
    merged: list[_Unit] = []
    for u in units:
        prev = merged[-1] if merged else None
        if (prev and u.page == prev.page + 1 and abs(prev.size - u.size) <= 0.6
                and not prev.bold and not u.bold and not prev.text.endswith(_TERMINAL + (":", '"', "”", "»", ")"))
                and u.text[:1].islower() and list_marker(u.text) is None):
            prev.text = f"{prev.text} {u.text}"
            prev.lines += u.lines
            prev.chars += u.chars
        else:
            merged.append(u)
    return merged


def _body_size(units: list[_Unit]) -> float:
    weights: Counter[float] = Counter()
    for u in units:
        weights[round(u.size * 2) / 2] += len(u.text)
    return weights.most_common(1)[0][0] if weights else 10.0


# --------------------------------------------------------------------------- títulos
def _is_heading(u: _Unit, nxt: _Unit | None, *, body: float, ratio: float,
                has_style: bool, bold_is_signal: bool) -> bool:
    text = u.text
    words = len(text.split())
    if words == 0 or len(text) > 160:
        return False
    if _BULLET.match(text) or text[:1].islower() or _CAPTION.match(text):
        return False
    ends_sentence = text.endswith(_TERMINAL)
    num = _NUM_HEAD.match(text)
    num_depth = num.group("num").count(".") + 1 if num else 0
    starts_upper = bool(re.match(r"^(?:\d+(?:\.\d+)*[.)]?\s+)?[A-ZÁÉÍÓÚÑ¿¡]", text))
    letters = [c for c in text if c.isalpha()]

    if has_style:
        if u.size >= body * ratio and words <= 25 and not ends_sentence and u.lines <= 3:
            return True
        if bold_is_signal and u.bold and words <= 14 and not ends_sentence and u.lines <= 2:
            return True
        if num and num_depth >= 2 and words <= 12 and not ends_sentence and starts_upper:
            return True
        if len(letters) >= 4 and text.isupper() and words <= 10 and not ends_sentence:
            return True
        return False

    # Texto plano: no hay tamaños ni negritas
    if len(letters) >= 3 and text.isupper() and words <= 10 and not ends_sentence:
        return True
    if num and words <= 12 and not ends_sentence and starts_upper and (num_depth >= 2 or _long(nxt)):
        return True
    if (words <= 10 and starts_upper and (not ends_sentence) and _long(nxt)
            and list_marker(text) is None):
        return True
    return False


def _long(unit: _Unit | None) -> bool:
    return bool(unit) and len(unit.text.split()) >= 15 and list_marker(unit.text) is None


def _assign_levels(headings: list[_Unit], numbered: dict[int, int]) -> dict[int, int]:
    """Nivel de cada título (clave: id del objeto). Prioriza el tamaño visual; usa la
    numeración si todos los títulos comparten el mismo estilo."""
    keys = sorted({(round(h.size * 2) / 2, h.bold) for h in headings}, reverse=True)
    rank = {k: i + 1 for i, k in enumerate(keys)}
    levels: dict[int, int] = {}
    for h in headings:
        if len(keys) > 1:
            lvl = rank[(round(h.size * 2) / 2, h.bold)]
        else:
            lvl = numbered.get(id(h), 1)
        levels[id(h)] = min(lvl, MAX_HEADING_LEVEL)
    return levels


# --------------------------------------------------------------------------- principal
def analyze_structure(extraction: Extraction, fallback_title: str) -> DocumentStructure:
    warnings: list[str] = []
    lines, toc_pages = _drop_toc_lines(extraction.lines)
    if toc_pages:
        shown = ", ".join(str(p) for p in toc_pages)
        warnings.append(f"Se omitió la tabla de contenido del documento (página {shown}).")
    units = _merge_across_pages(_build_units(lines))
    if not units:
        return DocumentStructure(fallback_title, 1, "filename", [], [], 0, extraction.page_count,
                                 ["No se encontró texto para analizar."])

    body = _body_size(units)
    ratio = HEADING_SIZE_RATIO_OCR if extraction.uses_ocr else HEADING_SIZE_RATIO_TEXT
    bold_share = sum(len(u.text) for u in units if u.bold) / max(1, sum(len(u.text) for u in units))
    bold_is_signal = extraction.has_style_info and not extraction.uses_ocr and bold_share < 0.5

    flags = [
        _is_heading(u, units[i + 1] if i + 1 < len(units) else None, body=body, ratio=ratio,
                    has_style=extraction.has_style_info, bold_is_signal=bold_is_signal)
        for i, u in enumerate(units)
    ]
    headings = [u for u, f in zip(units, flags) if f]

    # ---- título del documento
    title, title_page, title_source = fallback_title, 1, "filename"
    title_unit: _Unit | None = None
    if headings and extraction.has_style_info:
        first = headings[0]
        key = (round(first.size * 2) / 2, first.bold)
        same_style = [h for h in headings if (round(h.size * 2) / 2, h.bold) == key]
        position = next(i for i, u in enumerate(units) if u is first)
        if first.page == units[0].page and position < 8 and len(same_style) == 1:
            title_unit = first
    if title_unit is not None:
        title = clean_label(title_unit.text, 200) or fallback_title
        title_page, title_source = title_unit.page, "document"
        headings = [h for h in headings if h is not title_unit]
    elif extraction.metadata_title:
        title, title_source = extraction.metadata_title, "metadata"
    if title_source != "document":
        warnings.append(
            "No se detectó un título claro en el documento; se usó "
            + ("el título de los metadatos del PDF." if title_source == "metadata" else "el nombre del archivo.")
        )

    numbered = {}
    for h in headings:
        m = _NUM_HEAD.match(h.text)
        if m:
            numbered[id(h)] = m.group("num").count(".") + 1
    levels = _assign_levels(headings, numbered) if headings else {}

    # ---- árbol de secciones
    preamble: list[Block] = []
    roots: list[Section] = []
    stack: list[Section] = []
    for u in units:
        if u is title_unit:
            continue
        if id(u) in levels:
            level = levels[id(u)]
            section = Section(title=clean_label(u.text, 160) or u.text, raw_title=u.text,
                              level=level, page=u.page)
            while stack and stack[-1].level >= level:
                stack.pop()
            (stack[-1].children if stack else roots).append(section)
            stack.append(section)
            continue
        marker = list_marker(u.text)
        block = Block("list_item", marker[1], u.page) if marker else Block("paragraph", u.text, u.page)
        (stack[-1].blocks if stack else preamble).append(block)

    if not headings:
        warnings.append(
            "No se detectaron títulos ni subtítulos en el documento. El mapa se organizó por páginas "
            "y conviene revisarlo con cuidado."
        )
    elif extraction.uses_ocr:
        warnings.append("Parte del texto proviene de OCR: revisa posibles errores de reconocimiento.")
    if extraction.mean_confidence is not None and extraction.mean_confidence < 60:
        warnings.append(
            f"La confianza media del OCR es baja ({extraction.mean_confidence:.0f}/100); "
            "el texto puede contener errores."
        )
    return DocumentStructure(title=title, title_page=title_page, title_source=title_source,
                             preamble=preamble, sections=roots, heading_count=len(headings),
                             page_count=extraction.page_count, warnings=warnings)



def flatten_blocks(structure: DocumentStructure) -> list[dict]:
    """Párrafos y elementos de lista en orden de lectura, con su página y sección. Es el texto
    base de otros módulos (cuestionarios) y se guarda para no repetir la extracción/OCR."""
    out: list[dict] = []

    def add(blocks: list[Block], section: str | None) -> None:
        out.extend({"kind": b.kind, "text": b.text, "page": b.page, "section": section} for b in blocks)

    def walk(sec: Section) -> None:
        add(sec.blocks, sec.title)
        for child in sec.children:
            walk(child)

    add(structure.preamble, None)
    for sec in structure.sections:
        walk(sec)
    return out
