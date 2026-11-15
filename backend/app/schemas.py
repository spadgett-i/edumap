"""Modelos de datos (Pydantic). Son el contrato de la API y del mapa conceptual.

El mapa se valida siempre: ids únicos, conexiones con origen y destino existentes,
una sola raíz y sin ciclos en la jerarquía.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

NodeKind = Literal["root", "section", "definition", "list_item", "keyword", "manual"]
EdgeKind = Literal["hierarchy", "explicit", "cross", "manual"]


class MapNode(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    sourcePage: int | None = Field(default=None, ge=1)
    sourceText: str = Field(default="", max_length=20000)
    parentId: str | None = None
    kind: NodeKind = "section"
    # True cuando el algoritmo no tuvo evidencia suficiente: pide revisión humana.
    provisional: bool = False


class MapEdge(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    source: str
    target: str
    label: str = Field(default="", max_length=300)
    kind: EdgeKind = "hierarchy"
    provisional: bool = False
    # Procedencia de la relación (oración del documento donde se encontró el conector)
    sourceText: str = Field(default="", max_length=20000)
    sourcePage: int | None = Field(default=None, ge=1)


class ConceptMap(BaseModel):
    id: str
    documentId: str
    title: str = Field(min_length=1, max_length=300)
    nodes: list[MapNode]
    edges: list[MapEdge] = []
    warnings: list[str] = []
    meta: dict[str, Any] = {}

    @model_validator(mode="after")
    def _check_graph(self) -> "ConceptMap":
        if not self.nodes:
            raise ValueError("El mapa debe tener al menos un concepto.")

        ids = [n.id for n in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("Hay conceptos con identificadores repetidos.")
        by_id = {n.id: n for n in self.nodes}

        edge_ids = [e.id for e in self.edges]
        if len(set(edge_ids)) != len(edge_ids):
            raise ValueError("Hay relaciones con identificadores repetidos.")
        for e in self.edges:
            if e.source not in by_id:
                raise ValueError(f"La relación «{e.id}» apunta a un origen que no existe ({e.source}).")
            if e.target not in by_id:
                raise ValueError(f"La relación «{e.id}» apunta a un destino que no existe ({e.target}).")
            if e.source == e.target:
                raise ValueError(f"La relación «{e.id}» conecta un concepto consigo mismo.")

        roots = [n for n in self.nodes if n.parentId is None]
        if len(roots) != 1:
            raise ValueError("El mapa debe tener exactamente un concepto central (sin padre).")
        for n in self.nodes:
            if n.parentId is not None and n.parentId not in by_id:
                raise ValueError(f"El concepto «{n.label}» tiene un padre que no existe.")
            # Detección de ciclos siguiendo la cadena de padres
            seen = {n.id}
            cur = n.parentId
            while cur is not None:
                if cur in seen:
                    raise ValueError(f"La jerarquía tiene un ciclo en el concepto «{n.label}».")
                seen.add(cur)
                cur = by_id[cur].parentId
        return self


# ---------------------------------------------------------------- API (documentos y proyectos)
class StageOut(BaseModel):
    key: str
    label: str
    state: Literal["pending", "running", "done", "error"]


class DocumentOut(BaseModel):
    id: str
    originalName: str
    sizeBytes: int
    pageCount: int
    status: Literal["uploaded", "processing", "processed", "failed", "needs_review"]
    extractionMethod: str | None = None
    stages: list[StageOut]
    message: str | None = None
    projectId: str | None = None
    hasTextOverride: bool = False
    createdAt: str


class DocumentTextIn(BaseModel):
    text: str = Field(max_length=2_000_000)


class DocumentTextOut(BaseModel):
    text: str
    isManual: bool
    method: str | None = None


class ProjectSummary(BaseModel):
    id: str
    documentId: str
    documentName: str
    title: str
    resourceType: str
    createdAt: str
    updatedAt: str
    edited: bool
    nodeCount: int
    edgeCount: int


# ---------------------------------------------------------------- cuestionarios
class QuizRequest(BaseModel):
    maxPreguntas: int = Field(default=10, ge=1, le=30)


class QuizQuestion(BaseModel):
    id: str
    pregunta: str                     # oración con el espacio «______»
    opciones: list[str] = Field(min_length=2)
    respuestaCorrecta: str            # texto de la opción correcta
    tipo: Literal["definicion", "termino", "relacion"]
    seccion: str | None = None
    paginaOrigen: int | None = None
    oracionOriginal: str = ""         # procedencia: la oración completa del documento

    @model_validator(mode="after")
    def _check_options(self) -> "QuizQuestion":
        if len(set(self.opciones)) != len(self.opciones):
            raise ValueError("Las opciones de una pregunta no pueden repetirse.")
        if self.respuestaCorrecta not in self.opciones:
            raise ValueError("La respuesta correcta debe estar entre las opciones.")
        return self
