import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { Icon } from '../components/Icon'
import { Shell } from '../components/Shell'
import { paths } from '../lib/router'
import type { ProjectSummary } from '../types'

const RESOURCE_NAMES: Record<string, string> = { mapa_conceptual: 'Mapa conceptual' }
const fmtDate = (iso: string) =>
  new Date(iso).toLocaleString('es-MX', { dateStyle: 'medium', timeStyle: 'short' })

export function LibraryPage() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.listProjects().then(setProjects).catch((e) => setError(e instanceof ApiError ? e.message : 'No se pudo cargar la biblioteca.'))
  }, [])
  useEffect(load, [load])

  const remove = async (p: ProjectSummary) => {
    if (!window.confirm(`¿Eliminar «${p.documentName}»? Se borrarán el mapa y el PDF guardado en este equipo.`)) return
    try {
      await api.deleteProject(p.id)
      load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudo eliminar el proyecto.')
    }
  }

  return (
    <Shell active="library" title="Biblioteca de proyectos"
      actions={<a className="btn btn--primary" href={paths.upload}>Crear mapa conceptual</a>}>
      <div className="wide">
        <p className="notice">
          Los proyectos se guardan en la base de datos local de este equipo (SQLite). No se sincronizan con otros dispositivos.
        </p>
        {error && <div className="alert alert--error" role="alert"><Icon name="alert" /> <span>{error}</span></div>}

        {projects && projects.length === 0 && (
          <div className="empty">
            <h2>Aún no hay proyectos</h2>
            <p>Carga un PDF y EduMap generará el primer mapa conceptual.</p>
            <a className="btn btn--primary" href={paths.upload}>Crear mapa conceptual</a>
          </div>
        )}

        {projects && projects.length > 0 && (
          <ul className="project-list">
            {projects.map((p) => (
              <li key={p.id} className="project">
                <div className="project__icon"><Icon name="branch" size={22} /></div>
                <div className="project__body">
                  <h3 title={p.documentName}>{p.documentName}</h3>
                  <p className="project__title">{p.title}</p>
                  <p className="project__meta">
                    {RESOURCE_NAMES[p.resourceType] ?? p.resourceType} · {p.nodeCount} conceptos · {p.edgeCount} relaciones
                    · Creado {fmtDate(p.createdAt)}
                    {p.edited && <span className="tag">Editado</span>}
                  </p>
                </div>
                <div className="project__actions">
                  <a className="btn btn--primary" href={paths.editor(p.id)}>Abrir mapa</a>
                  <a className="btn btn--secondary" href={paths.quiz(p.id)}>Cuestionario</a>
                  <button className="btn btn--danger-ghost" onClick={() => remove(p)} aria-label={`Eliminar ${p.documentName}`}>
                    <Icon name="trash" /> Eliminar
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Shell>
  )
}
