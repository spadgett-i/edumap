"""Endpoints de proyectos: biblioteca, lectura/edición del mapa, restablecer y eliminar."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from ..database import Database
from ..schemas import ConceptMap, ProjectSummary, QuizQuestion, QuizRequest
from ..services.concept_map import normalize_hierarchy
from ..services.pdf_extractor import ExtractionError
from ..services.pipeline import ensure_blocks
from ..services.quiz import build_quiz

router = APIRouter(prefix="/api/projects", tags=["proyectos"])


def _db(request: Request) -> Database:
    return request.app.state.db


def _get_or_404(db: Database, project_id: str) -> dict:
    project = db.get_project(project_id)
    if project is None:
        raise HTTPException(404, "El proyecto no existe.")
    return project


def _summary(row: dict) -> ProjectSummary:
    cmap = ConceptMap.model_validate_json(row["map_json"])
    return ProjectSummary(
        id=row["id"], documentId=row["document_id"], documentName=row["document_name"],
        title=row["title"], resourceType=row["resource_type"], createdAt=row["created_at"],
        updatedAt=row["updated_at"], edited=bool(row["edited"]),
        nodeCount=len(cmap.nodes), edgeCount=len(cmap.edges),
    )


@router.get("", response_model=list[ProjectSummary])
def list_projects(request: Request) -> list[ProjectSummary]:
    return [_summary(r) for r in _db(request).list_projects()]


@router.get("/{project_id}", response_model=ProjectSummary)
def get_project(project_id: str, request: Request) -> ProjectSummary:
    return _summary(_get_or_404(_db(request), project_id))


@router.get("/{project_id}/map", response_model=ConceptMap)
def get_map(project_id: str, request: Request) -> ConceptMap:
    row = _get_or_404(_db(request), project_id)
    return ConceptMap.model_validate_json(row["map_json"])


@router.put("/{project_id}/map", response_model=ConceptMap)
def save_map(project_id: str, body: ConceptMap, request: Request) -> ConceptMap:
    db = _db(request)
    row = _get_or_404(db, project_id)
    # El servidor decide la identidad; el cliente solo aporta el contenido del mapa.
    cmap = normalize_hierarchy(body.model_copy(update={"id": project_id, "documentId": row["document_id"]}))
    original = ConceptMap.model_validate_json(row["original_map_json"])
    edited = (cmap.nodes != original.nodes) or (cmap.edges != original.edges) or (cmap.title != original.title)
    db.save_project_map(project_id, title=cmap.title, map_json=cmap.model_dump_json(), edited=edited)
    return cmap


@router.post("/{project_id}/map/reset", response_model=ConceptMap)
def reset_map(project_id: str, request: Request) -> ConceptMap:
    db = _db(request)
    row = _get_or_404(db, project_id)
    original = ConceptMap.model_validate_json(row["original_map_json"])
    db.save_project_map(project_id, title=original.title, map_json=original.model_dump_json(), edited=False)
    return original


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, request: Request) -> Response:
    db = _db(request)
    _get_or_404(db, project_id)
    project = db.delete_project(project_id)
    if project:
        doc = db.get_document(project["document_id"])
        if doc:
            (request.app.state.settings.upload_dir / doc["stored_name"]).unlink(missing_ok=True)
            db.delete_document(doc["id"])
    return Response(status_code=204)


@router.post("/{project_id}/quiz", response_model=list[QuizQuestion])
def generate_quiz(project_id: str, request: Request, body: QuizRequest | None = None) -> list[QuizQuestion]:
    """Genera el cuestionario (completar la oración) a partir del texto extraído del documento.

    Es determinista: el mismo documento produce siempre las mismas preguntas y el mismo orden de opciones.
    Devuelve una lista vacía si el documento no tiene oraciones aptas (definiciones o relaciones claras).
    """
    db = _db(request)
    row = _get_or_404(db, project_id)
    doc = db.get_document(row["document_id"])
    if doc is None:
        raise HTTPException(404, "El documento original de este proyecto ya no existe.")
    try:
        blocks = ensure_blocks(db, request.app.state.settings, doc)
    except ExtractionError as exc:
        raise HTTPException(422, str(exc)) from exc
    cmap = ConceptMap.model_validate_json(row["map_json"])
    return build_quiz(blocks, cmap, (body or QuizRequest()).maxPreguntas)
