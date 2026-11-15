"""Orquesta el procesamiento de un documento y registra el estado real de cada etapa."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from ..config import Settings
from ..database import Database, new_id
from .concept_map import build_concept_map
from .pdf_extractor import (
    MIN_WORDS_TOTAL, ExtractionError, extract_document, extraction_from_text,
)
from .structure import analyze_structure, flatten_blocks

log = logging.getLogger("edumap.pipeline")

STAGES = [
    ("recepcion", "Recepción del documento"),
    ("extraccion", "Extracción del texto"),
    ("estructura", "Identificación de la estructura"),
    ("mapa", "Generación del mapa conceptual"),
    ("preparacion", "Preparación del recurso interactivo"),
]
STAGE_KEYS = [k for k, _ in STAGES]


def initial_stages() -> dict[str, str]:
    return {k: ("done" if k == "recepcion" else "pending") for k in STAGE_KEYS}


def _fallback_title(original_name: str) -> str:
    stem = re.sub(r"\.pdf$", "", original_name, flags=re.IGNORECASE)
    return re.sub(r"[_\s]+", " ", stem).strip() or "Documento sin título"


def run_pipeline(db: Database, settings: Settings, doc_id: str) -> None:
    doc = db.get_document(doc_id)
    if doc is None:
        return
    stages = initial_stages()

    def set_stage(key: str, state: str) -> None:
        stages[key] = state
        db.update_document(doc_id, stages=stages)

    current = "extraccion"
    try:
        # ---- 2. Extracción del texto
        set_stage("extraccion", "running")
        override = doc.get("text_override")
        if override:
            extraction = extraction_from_text(override, doc["page_count"])
        else:
            extraction = extract_document(settings.upload_dir / doc["stored_name"], settings)
        db.update_document(doc_id, extraction_method=extraction.method,
                           extracted_text=extraction.as_plain_text())
        if extraction.word_count < MIN_WORDS_TOTAL:
            status = "needs_review" if extraction.uses_ocr or extraction.method == "manual" else "failed"
            msg = ("El OCR no obtuvo texto suficiente. Revisa el texto reconocido, complétalo a mano o sube otro archivo."
                   if status == "needs_review"
                   else "No se encontró texto suficiente en el documento.")
            set_stage("extraccion", "error")
            db.update_document(doc_id, status=status, message=msg)
            return
        set_stage("extraccion", "done")

        # ---- 3. Identificación de la estructura
        current = "estructura"
        set_stage("estructura", "running")
        structure = analyze_structure(extraction, _fallback_title(doc["original_name"]))
        db.update_document(doc_id, blocks_json=json.dumps(flatten_blocks(structure), ensure_ascii=False))
        set_stage("estructura", "done")

        # ---- 4. Generación del mapa conceptual
        current = "mapa"
        set_stage("mapa", "running")
        project_id = new_id("proyecto")
        cmap = build_concept_map(structure, project_id=project_id, document_id=doc_id,
                                 extraction_method=extraction.method)
        cmap.warnings = [*extraction.warnings, *cmap.warnings]
        set_stage("mapa", "done")

        # ---- 5. Preparación del recurso interactivo
        current = "preparacion"
        set_stage("preparacion", "running")
        db.insert_project(project_id=project_id, document_id=doc_id, document_name=doc["original_name"],
                          title=cmap.title, map_json=cmap.model_dump_json())
        set_stage("preparacion", "done")
        db.update_document(doc_id, status="processed", project_id=project_id, message=None)
    except ExtractionError as exc:
        stages[current] = "error"
        db.update_document(doc_id, stages=stages, status="failed", message=str(exc))
    except Exception:  # error inesperado: se registra completo y se muestra un mensaje genérico
        log.exception("Error inesperado procesando %s", doc_id)
        stages[current] = "error"
        db.update_document(doc_id, stages=stages, status="failed",
                           message="Ocurrió un error inesperado al procesar el documento. "
                                   "Prueba con otro archivo o revisa la consola del servidor.")


def ensure_blocks(db: Database, settings: Settings, doc: dict) -> list[dict]:
    """Bloques de texto del documento (para cuestionarios). Los documentos procesados antes de
    existir este módulo no los tienen guardados: se reconstruyen una vez con la misma lógica."""
    if doc.get("blocks_json"):
        return json.loads(doc["blocks_json"])
    if doc.get("text_override"):
        extraction = extraction_from_text(doc["text_override"], doc["page_count"])
    else:
        extraction = extract_document(settings.upload_dir / doc["stored_name"], settings)
    structure = analyze_structure(extraction, _fallback_title(doc["original_name"]))
    blocks = flatten_blocks(structure)
    db.update_document(doc["id"], blocks_json=json.dumps(blocks, ensure_ascii=False))
    return blocks
