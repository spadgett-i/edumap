import type { ConceptMap, DocumentInfo, DocumentText, Health, ProjectSummary, QuizQuestion } from './types'

const BASE = import.meta.env.VITE_API_URL ?? ''

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

/** Convierte la respuesta de error de FastAPI en un mensaje legible. */
function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => String((d as { msg?: string }).msg ?? '').replace(/^Value error, /, ''))
      .filter(Boolean)
      .join(' ')
  }
  return fallback
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, init)
  } catch {
    throw new ApiError('No se pudo conectar con el servidor. ¿Está el backend en ejecución (puerto 8000)?', 0)
  }
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(errorMessage(body, `Error del servidor (${res.status}).`), res.status)
  return body as T
}

const json = (method: string, data: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data),
})

export const api = {
  health: () => request<Health>('/api/health'),

  /** Subida con XMLHttpRequest para informar el avance real de bytes enviados. */
  uploadDocument(file: File, onProgress: (fraction: number) => void): Promise<DocumentInfo> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${BASE}/api/documents`)
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
      xhr.onerror = () =>
        reject(new ApiError('No se pudo conectar con el servidor. ¿Está el backend en ejecución (puerto 8000)?', 0))
      xhr.onload = () => {
        let body: unknown = null
        try { body = JSON.parse(xhr.responseText) } catch { /* sin cuerpo JSON */ }
        if (xhr.status >= 200 && xhr.status < 300) resolve(body as DocumentInfo)
        else reject(new ApiError(errorMessage(body, `Error del servidor (${xhr.status}).`), xhr.status))
      }
      const form = new FormData()
      form.append('file', file)
      xhr.send(form)
    })
  },

  processDocument: (id: string) => request<DocumentInfo>(`/api/documents/${id}/process`, { method: 'POST' }),
  getDocument: (id: string) => request<DocumentInfo>(`/api/documents/${id}`),
  getDocumentText: (id: string) => request<DocumentText>(`/api/documents/${id}/text`),
  putDocumentText: (id: string, text: string) =>
    request<DocumentText>(`/api/documents/${id}/text`, json('PUT', { text })),

  listProjects: () => request<ProjectSummary[]>('/api/projects'),
  getMap: (id: string) => request<ConceptMap>(`/api/projects/${id}/map`),
  saveMap: (id: string, map: ConceptMap) => request<ConceptMap>(`/api/projects/${id}/map`, json('PUT', map)),
  resetMap: (id: string) => request<ConceptMap>(`/api/projects/${id}/map/reset`, { method: 'POST' }),
  generateQuiz: (id: string, maxPreguntas = 10) =>
    request<QuizQuestion[]>(`/api/projects/${id}/quiz`, json('POST', { maxPreguntas })),
  deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: 'DELETE' }),
}
