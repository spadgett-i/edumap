"""Extracción de texto (ruta A), OCR (ruta B) y detección de estructura."""
import pymupdf
import pytest

from app.config import Settings
from app.services import pdf_extractor
from app.services.pdf_extractor import (
    ExtractionError, OcrUnavailableError, PdfOpenError, extract_document, extraction_from_text,
    inspect_pdf, ocr_available,
)
from app.services.structure import analyze_structure

SETTINGS = Settings()


def test_extrae_texto_de_pdf_valido(sample_pdf):
    ex = extract_document(sample_pdf, SETTINGS)
    text = " ".join(l.text for l in ex.lines).lower()
    assert ex.method == "text"
    assert ex.page_count == 2
    assert "memoria de trabajo" in text
    assert "mapa conceptual" in text
    assert {l.page for l in ex.lines} == {1, 2}


def test_detecta_titulo_y_jerarquia(sample_pdf):
    st = analyze_structure(extract_document(sample_pdf, SETTINGS), "respaldo")
    assert st.title == "Fundamentos del Aprendizaje Multimedia"
    assert st.title_source == "document"
    assert [s.title for s in st.sections] == ["Introducción", "Carga cognitiva", "Principios de diseño"]
    intro = st.sections[0]
    assert [c.title for c in intro.children] == ["Canales de procesamiento"]
    assert intro.level == 1 and intro.children[0].level == 2
    kinds = [b.kind for b in intro.children[0].blocks]
    assert kinds.count("list_item") == 3 and kinds.count("paragraph") == 1


def test_quita_encabezados_y_numeros_de_pagina(tmp_path):
    doc = pymupdf.open()
    for i in range(4):
        page = doc.new_page()
        page.insert_text((72, 30), "Universidad Ejemplo - Apuntes", fontsize=9)
        page.insert_text((72, 100), f"Contenido único de la página {i + 1} con suficiente texto para contarse.", fontsize=11)
        page.insert_text((290, 815), f"{i + 1}", fontsize=9)
    path = tmp_path / "margenes.pdf"
    doc.save(path)
    ex = extract_document(path, SETTINGS)
    texts = [l.text for l in ex.lines]
    assert not any("Universidad Ejemplo" in t for t in texts)
    assert all(not t.isdigit() for t in texts)
    assert len(texts) == 4


def test_pdf_danado_y_cifrado(tmp_path):
    bad = tmp_path / "malo.pdf"
    bad.write_bytes(b"%PDF-1.4\nesto no es un pdf real")
    with pytest.raises(PdfOpenError):
        inspect_pdf(bad)

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "secreto " * 20)
    enc = tmp_path / "cifrado.pdf"
    doc.save(enc, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="clave", owner_pw="clave")
    with pytest.raises(PdfOpenError, match="contraseña"):
        inspect_pdf(enc)


def test_limite_de_paginas(sample_pdf):
    with pytest.raises(ExtractionError, match="límite"):
        extract_document(sample_pdf, Settings(max_pages=1))


def test_texto_manual_construye_extraccion():
    ex = extraction_from_text("[[Página 2]]\n\nIntroducción\n\nUn párrafo.\nque continúa aquí.\n")
    assert ex.method == "manual" and not ex.has_style_info
    assert [l.page for l in ex.lines] == [2, 2, 2]
    assert len({l.block for l in ex.lines}) == 2        # título y párrafo; las dos líneas del párrafo comparten bloque


def test_pdf_escaneado_sin_ocr_da_mensaje_claro(scanned_pdf, monkeypatch):
    monkeypatch.setattr(pdf_extractor, "ocr_available", lambda settings: False)
    with pytest.raises(OcrUnavailableError, match="Tesseract"):
        extract_document(scanned_pdf, SETTINGS)


@pytest.mark.skipif(not ocr_available(SETTINGS), reason="Tesseract OCR no está instalado")
def test_ocr_de_pdf_escaneado(scanned_pdf):
    ex = extract_document(scanned_pdf, SETTINGS)
    text = " ".join(l.text for l in ex.lines).lower()
    assert ex.method == "ocr"
    assert ex.word_count > 150
    assert "memoria" in text and "carga" in text
    structure = analyze_structure(ex, "respaldo")
    assert structure.heading_count >= 3          # los títulos se infieren por altura de línea y numeración


def test_omite_tabla_de_contenido_y_pies_de_figura():
    from app.services.pdf_extractor import Line
    from app.services.structure import _drop_toc_lines
    toc = [Line(f"{i}.1 Apartado número {i}", 2, 11, False, 1) for i in range(1, 7)]
    toc += [Line(str(i + 3), 2, 11, False, 1) for i in range(6)]
    body = [Line("Texto normal del documento que debe conservarse.", 3, 11, False, 2)]
    kept, pages = _drop_toc_lines(toc + body)
    assert pages == [2]
    assert [l.text for l in kept if l.page == 3] == ["Texto normal del documento que debe conservarse."]
    assert not [l for l in kept if l.page == 2 and l.text.strip().isdigit()]


def test_un_pie_de_figura_no_es_un_titulo(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    y = 80
    for text, font, size in [("Documento de prueba", "hebo", 20), ("Introducción", "hebo", 14),
                             ("Este es un párrafo de texto normal con suficientes palabras para el cuerpo.", "helv", 11),
                             ("Figura 7", "hebo", 14),
                             ("Otro párrafo posterior con texto normal para completar la página de ejemplo.", "helv", 11)]:
        page.insert_text((72, y), text, fontname=font, fontsize=size)
        y += 40
    path = tmp_path / "fig.pdf"
    doc.save(path)
    st = analyze_structure(extract_document(path, SETTINGS), "x")
    assert [s.title for s in st.sections] == ["Introducción"]
