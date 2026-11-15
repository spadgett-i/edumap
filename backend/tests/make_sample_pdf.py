"""Genera PDF de ejemplo para probar EduMap (solo usa PyMuPDF).

    python tests/make_sample_pdf.py            # escribe en ../samples/

- ejemplo_aprendizaje_multimedia.pdf : PDF con texto seleccionable (ruta A)
- ejemplo_escaneado.pdf              : las mismas páginas convertidas en imágenes (ruta B, requiere OCR)

El contenido es un texto didáctico breve escrito para las pruebas.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

PAGE_W, PAGE_H = 595, 842
MARGIN = 64

# (tipo, texto). Tipos: title, h1, h2, p, li
CONTENT: list[tuple[str, str]] = [
    ("title", "Fundamentos del Aprendizaje Multimedia"),
    ("p", "Este documento resume ideas básicas sobre cómo se aprende con palabras e imágenes y cómo "
          "diseñar materiales digitales que no saturen la atención del estudiante."),
    ("h1", "1. Introducción"),
    ("p", "El aprendizaje multimedia estudia cómo las personas aprenden a partir de palabras e imágenes. "
          "La Teoría Cognitiva del Aprendizaje Multimedia se define como un marco que explica cómo el "
          "estudiante selecciona, organiza e integra la información. El aprendizaje multimedia ocurre "
          "cuando el material combina texto, imágenes y sonido de forma coherente."),
    ("h2", "1.1 Canales de procesamiento"),
    ("p", "El canal visual es un sistema de procesamiento que recibe imágenes e ilustraciones. "
          "El canal auditivo es un sistema que procesa palabras habladas y sonidos. "
          "La memoria de trabajo permite integrar la información de ambos canales. "
          "La memoria de trabajo tiene una capacidad limitada, por lo que el diseño del material importa."),
    ("li", "Memoria sensorial: recibe la información por los ojos y los oídos"),
    ("li", "Memoria de trabajo: selecciona y organiza la información entrante"),
    ("li", "Memoria a largo plazo: almacena los conocimientos previos del estudiante"),
    ("h1", "2. Carga cognitiva"),
    ("p", "La carga cognitiva se refiere a la cantidad de esfuerzo mental que utiliza la memoria de trabajo. "
          "La carga cognitiva aumenta cuando el material tiene demasiados elementos que distraen. "
          "Reducir la carga cognitiva ayuda al estudiante a seguir el tema."),
    ("h2", "2.1 Tipos de carga"),
    ("li", "Carga intrínseca"),
    ("li", "Carga extrínseca"),
    ("li", "Carga pertinente"),
    ("p", "La carga extrínseca depende de la forma de presentar el material. La carga extrínseca se reduce "
          "con diseños limpios y con la memoria de trabajo libre de distracciones. "
          "La carga extrínseca afecta a la memoria de trabajo."),
    ("h1", "3. Principios de diseño"),
    ("p", "El principio de coherencia consiste en eliminar el material que no ayuda al aprendizaje. "
          "La señalización permite resaltar la información esencial. "
          "La contigüidad espacial incluye colocar el texto cerca de la imagen que explica. "
          "El principio de coherencia reduce la carga cognitiva."),
    ("h2", "3.1 Aplicación en mapas conceptuales"),
    ("p", "Un mapa conceptual es una representación gráfica que organiza conceptos mediante nodos y palabras "
          "de enlace. El mapa conceptual facilita el aprendizaje significativo porque muestra la jerarquía "
          "del contenido. Cada mapa conceptual reduce la carga cognitiva cuando se presenta por niveles."),
]

STYLES = {  # fuente, tamaño, espacio antes, espacio después
    "title": ("hebo", 22, 0, 14),
    "h1": ("hebo", 16, 16, 6),
    "h2": ("hebo", 13, 10, 4),
    "p": ("helv", 11, 0, 8),
    "li": ("helv", 11, 0, 3),
}
LEADING = 1.35


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if pymupdf.get_text_length(candidate, fontname=font, fontsize=size) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def build_text_pdf(path: Path, content: list[tuple[str, str]] = CONTENT) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    y = MARGIN
    for kind, text in content:
        font, size, before, after = STYLES[kind]
        indent = 18 if kind == "li" else 0
        lines = _wrap(text, font, size, PAGE_W - 2 * MARGIN - indent - (12 if kind == "li" else 0))
        height = before + len(lines) * size * LEADING + after
        if y + height > PAGE_H - MARGIN:
            page = doc.new_page(width=PAGE_W, height=PAGE_H)
            y = MARGIN
        y += before
        for i, line in enumerate(lines):
            y += size * LEADING
            x = MARGIN + indent
            if kind == "li":
                if i == 0:
                    page.insert_text((MARGIN + 4, y), "•", fontname="helv", fontsize=size)
                x += 12
            page.insert_text((x, y), line, fontname=font, fontsize=size)
        y += after
    doc.save(path)
    doc.close()


def build_scanned_pdf(source: Path, target: Path, dpi: int = 200) -> None:
    """Convierte cada página en una imagen: simula un documento escaneado sin capa de texto."""
    src = pymupdf.open(source)
    out = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, stream=pix.tobytes("jpg", jpg_quality=70))   # JPEG: pesa poco, como un escaneo real
    out.save(target)
    out.close()
    src.close()


if __name__ == "__main__":
    dest = Path(__file__).resolve().parents[2] / "samples"
    dest.mkdir(exist_ok=True)
    text_pdf = dest / "ejemplo_aprendizaje_multimedia.pdf"
    build_text_pdf(text_pdf)
    build_scanned_pdf(text_pdf, dest / "ejemplo_escaneado.pdf")
    print("Generados:", *sorted(p.name for p in dest.glob("*.pdf")), sep="\n  ", file=sys.stdout)
