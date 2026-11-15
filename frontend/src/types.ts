// Contrato con el backend (ver backend/app/schemas.py).
export type NodeKind = 'root' | 'section' | 'definition' | 'list_item' | 'keyword' | 'manual'
export type EdgeKind = 'hierarchy' | 'explicit' | 'cross' | 'manual'

export interface MapNode {
  id: string
  label: string
  description: string
  sourcePage: number | null
  sourceText: string
  parentId: string | null
  kind: NodeKind
  provisional: boolean
}

export interface MapEdge {
  id: string
  source: string
  target: string
  label: string
  kind: EdgeKind
  provisional: boolean
  sourceText: string
  sourcePage: number | null
}

export interface ConceptMap {
  id: string
  documentId: string
  title: string
  nodes: MapNode[]
  edges: MapEdge[]
  warnings: string[]
  meta: Record<string, unknown>
}

export type StageState = 'pending' | 'running' | 'done' | 'error'
export interface Stage { key: string; label: string; state: StageState }

export type DocumentStatus = 'uploaded' | 'processing' | 'processed' | 'failed' | 'needs_review'
export interface DocumentInfo {
  id: string
  originalName: string
  sizeBytes: number
  pageCount: number
  status: DocumentStatus
  extractionMethod: string | null
  stages: Stage[]
  message: string | null
  projectId: string | null
  hasTextOverride: boolean
  createdAt: string
}

export interface ProjectSummary {
  id: string
  documentId: string
  documentName: string
  title: string
  resourceType: string
  createdAt: string
  updatedAt: string
  edited: boolean
  nodeCount: number
  edgeCount: number
}

export interface Health { status: string; maxUploadMb: number; ocr: boolean; ocrLanguages: string[] }
export interface DocumentText { text: string; isManual: boolean; method: string | null }

export interface QuizQuestion {
  id: string
  pregunta: string            // oración con el espacio «______»
  opciones: string[]
  respuestaCorrecta: string
  tipo: 'definicion' | 'termino' | 'relacion'
  seccion: string | null
  paginaOrigen: number | null
  oracionOriginal: string
}
