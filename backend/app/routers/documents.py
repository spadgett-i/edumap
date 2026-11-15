"""Endpoints de documentos: subir PDF, procesarlo y consultar su estado."""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile

from ..database import Database
from ..schemas import DocumentOut, DocumentTextIn, DocumentTextOut, StageOut
from ..services.pdf_extractor import PdfOpenError, inspect_pdf
from ..services.pipeline import STAGES, initial_stages, run_pipeline

router = APIRouter(prefix="/api/documents", tags=["documentos"])

CHUNK = 1024 * 1024


def _db(request: Request) -> Database:
    return request.app.state.db


def _settings(request: Request):
    return request.app.state.settings


def safe_display_name(raw: str | None) -> str:
    """Nombre solo para mostrar. Nunca se usa para construir rutas en disco."""
    name = os.path.basename((raw or "documento.pdf").replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:150] or "documento.pdf"


def to_out(doc: dict) -> DocumentOut:
    states = json.loads(doc["stages"])
    return DocumentOut(
        id=doc["id"], originalName=doc["original_name"], sizeBytes=doc["size_bytes"],
        pageCount=doc["page_count"], status=doc["status"], extractionMethod=doc["extraction_method"],
        stages=[StageOut(key=k, label=label, state=states.get(k, "pending")) for k, label in STAGES],
        message=doc["message"], projectId=doc["project_id"],
        hasTextOverride=bool(doc["text_override"]), createdAt=doc["created_at"],
    )


def _get_or_404(db: Database, doc_id: str) -> dict:
    doc = db.get_document(doc_id)
    if doc is None:
        raise HTTPException(404, "El documento no existe.")
    return doc


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(request: Request, file: UploadFile = File(...)) -> DocumentOut:
    settings, db = _settings(request), _db(request)
    display_name = safe_display_name(file.filename)
    if not display_name.lower().endswith(".pdf"):
        raise HTTPException(415, "Solo se aceptan archivos PDF (.pdf).")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    doc_id = f"documento-{uuid.uuid4().hex[:12]}"
    stored_name = f"{doc_id}.pdf"                       # nombre interno generado por el servidor
    tmp_path = settings.upload_dir / f".tmp-{uuid.uuid4().hex}"
    final_path = settings.upload_dir / stored_name
    size = 0
    try:
        with open(tmp_path, "wb") as out:
            head = b""
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(413, f"El archivo supera el límite de {settings.max_upload_mb} MB.")
                if len(head) < 1024:
                    head += chunk[: 1024 - len(head)]
                out.write(chunk)
        if size == 0:
            raise HTTPException(422, "El archivo está vacío.")
        if b"%PDF-" not in head:
            raise HTTPException(415, "El archivo no tiene formato PDF válido (aunque termine en .pdf).")
        try:
            page_count = inspect_pdf(tmp_path)
        except PdfOpenError as exc:
            raise HTTPException(422, str(exc)) from exc
        os.replace(tmp_path, final_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    db.insert_document(doc_id=doc_id, original_name=display_name, stored_name=stored_name,
                       size_bytes=size, page_count=page_count, stages=initial_stages())
    return to_out(db.get_document(doc_id))


@router.post("/{doc_id}/process", response_model=DocumentOut, status_code=202)
def process_document(doc_id: str, request: Request, background: BackgroundTasks) -> DocumentOut:
    settings, db = _settings(request), _db(request)
    doc = _get_or_404(db, doc_id)
    if doc["status"] == "processing":
        raise HTTPException(409, "El documento ya se está procesando.")
    if doc["status"] == "processed":
        raise HTTPException(409, "El documento ya fue procesado. Ábrelo desde la biblioteca de proyectos.")
    db.update_document(doc_id, status="processing", message=None, stages=initial_stages())
    background.add_task(run_pipeline, db, settings, doc_id)
    return to_out(db.get_document(doc_id))


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: str, request: Request) -> DocumentOut:
    return to_out(_get_or_404(_db(request), doc_id))


@router.get("/{doc_id}/text", response_model=DocumentTextOut)
def get_document_text(doc_id: str, request: Request) -> DocumentTextOut:
    doc = _get_or_404(_db(request), doc_id)
    manual = bool(doc["text_override"])
    return DocumentTextOut(text=doc["text_override"] if manual else (doc["extracted_text"] or ""),
                           isManual=manual, method=doc["extraction_method"])


@router.put("/{doc_id}/text", response_model=DocumentTextOut)
def put_document_text(doc_id: str, body: DocumentTextIn, request: Request) -> DocumentTextOut:
    db = _db(request)
    doc = _get_or_404(db, doc_id)
    if doc["status"] in ("processing", "processed"):
        raise HTTPException(409, "No se puede cambiar el texto de un documento procesado o en proceso.")
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "El texto no puede estar vacío.")
    db.update_document(doc_id, text_override=text)
    return DocumentTextOut(text=text, isManual=True, method=doc["extraction_method"])
