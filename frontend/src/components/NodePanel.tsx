import { Icon } from './Icon'
import { descendantsOf, hierarchyEdgeOf, countProvisional } from '../lib/mapOps'
import type { ConceptMap, EdgeKind, NodeKind } from '../types'

export type Selection = { type: 'node' | 'edge'; id: string } | null

const NODE_KIND: Record<NodeKind, string> = {
  root: 'Concepto central (título del documento)',
  section: 'Sección del documento',
  definition: 'Definición encontrada en el texto',
  list_item: 'Elemento de una lista',
  keyword: 'Término repetido (palabra clave)',
  manual: 'Creado manualmente',
}
const EDGE_KIND: Record<EdgeKind, string> = {
  hierarchy: 'Relación jerárquica',
  explicit: 'Relación con conector explícito en el texto',
  cross: 'Relación por co-mención (provisional)',
  manual: 'Relación creada manualmente',
}

export interface PanelActions {
  select: (s: Selection) => void
  reveal: (nodeId: string) => void
  updateNode: (id: string, patch: { label?: string; description?: string; provisional?: boolean }) => void
  updateEdge: (id: string, patch: { label?: string; provisional?: boolean }) => void
  setParent: (id: string, parentId: string) => void
  addChild: (parentId: string) => void
  deleteNode: (id: string) => void
  deleteEdge: (id: string) => void
}

const short = (s: string, n = 48) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)

export function NodePanel({ map, selection, actions }: { map: ConceptMap; selection: Selection; actions: PanelActions }) {
  const byId = new Map(map.nodes.map((n) => [n.id, n]))

  if (selection?.type === 'node' && byId.has(selection.id)) {
    const node = byId.get(selection.id)!
    const parentEdge = hierarchyEdgeOf(map, node.id)
    const blocked = descendantsOf(map.nodes, node.id)
    const parentOptions = map.nodes.filter((n) => n.id !== node.id && !blocked.has(n.id))
    const links = map.edges.filter((e) => e.kind !== 'hierarchy' && (e.source === node.id || e.target === node.id))
    const hierarchyProvisional = parentEdge?.provisional ?? false

    return (
      <div className="panel__body">
        <p className="panel__kind">{NODE_KIND[node.kind]}</p>
        {(node.provisional || hierarchyProvisional) && (
          <div className="alert alert--warn alert--compact" role="status">
            <Icon name="alert" size={16} />
            <span>El algoritmo no tuvo evidencia explícita para este elemento. Revísalo.</span>
            <button className="btn btn--ghost btn--sm" onClick={() => {
              actions.updateNode(node.id, { provisional: false })
              if (parentEdge) actions.updateEdge(parentEdge.id, { provisional: false })
            }}>Confirmar</button>
          </div>
        )}

        <label className="field">
          <span className="field__label">Texto del concepto</span>
          <input type="text" value={node.label} maxLength={300}
            aria-invalid={!node.label.trim()} onChange={(e) => actions.updateNode(node.id, { label: e.target.value })} />
          {!node.label.trim() && <span className="field__error">El concepto necesita un texto.</span>}
        </label>

        <label className="field">
          <span className="field__label">Descripción</span>
          <textarea rows={4} value={node.description}
            onChange={(e) => actions.updateNode(node.id, { description: e.target.value })} />
        </label>

        <div className="source">
          <p className="field__label">
            Fragmento de origen{node.sourcePage ? ` · página ${node.sourcePage}` : ''}
          </p>
          {node.sourceText
            ? <blockquote>{node.sourceText}</blockquote>
            : <p className="muted">Este concepto no proviene del documento: lo creaste tú.</p>}
        </div>

        {node.parentId && parentEdge && (
          <fieldset className="field-group">
            <legend>Posición en la jerarquía</legend>
            <label className="field">
              <span className="field__label">Concepto padre</span>
              <select value={node.parentId} onChange={(e) => actions.setParent(node.id, e.target.value)}>
                {parentOptions.map((n) => <option key={n.id} value={n.id}>{short(n.label)}</option>)}
              </select>
            </label>
            <label className="field">
              <span className="field__label">Relación con el padre</span>
              <input type="text" value={parentEdge.label} maxLength={300}
                onChange={(e) => actions.updateEdge(parentEdge.id, { label: e.target.value })} />
            </label>
          </fieldset>
        )}

        {links.length > 0 && (
          <div className="links">
            <p className="field__label">Otras relaciones</p>
            <ul>
              {links.map((e) => {
                const other = byId.get(e.source === node.id ? e.target : e.source)
                return (
                  <li key={e.id}>
                    <button className="linkbtn" onClick={() => actions.select({ type: 'edge', id: e.id })}>
                      {e.source === node.id ? '→' : '←'} {e.label || 'sin etiqueta'} · {short(other?.label ?? '?', 34)}
                      {e.provisional && ' (revisar)'}
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        )}

        <div className="panel__actions">
          <button className="btn btn--secondary" onClick={() => actions.addChild(node.id)}>
            <Icon name="plus" /> Agregar concepto hijo
          </button>
          <button className="btn btn--danger-ghost" disabled={node.parentId === null}
            title={node.parentId === null ? 'El concepto central no se puede eliminar' : undefined}
            onClick={() => window.confirm(`¿Eliminar «${short(node.label)}»? Sus conceptos hijos pasarán a su padre.`) && actions.deleteNode(node.id)}>
            <Icon name="trash" /> Eliminar concepto
          </button>
        </div>
        <p className="panel__tip">Para relacionar dos conceptos, arrastra desde el punto derecho de uno hasta el punto izquierdo de otro.</p>
      </div>
    )
  }

  if (selection?.type === 'edge') {
    const edge = map.edges.find((e) => e.id === selection.id)
    if (edge) {
      const src = byId.get(edge.source)
      const dst = byId.get(edge.target)
      return (
        <div className="panel__body">
          <p className="panel__kind">{EDGE_KIND[edge.kind]}</p>
          <p className="edge-path">
            <button className="linkbtn" onClick={() => actions.select({ type: 'node', id: edge.source })}>{short(src?.label ?? '?', 40)}</button>
            <span aria-hidden="true"> → </span>
            <button className="linkbtn" onClick={() => actions.select({ type: 'node', id: edge.target })}>{short(dst?.label ?? '?', 40)}</button>
          </p>
          {edge.provisional && (
            <div className="alert alert--warn alert--compact" role="status">
              <Icon name="alert" size={16} />
              <span>Relación provisional: revisa si tiene sentido.</span>
              <button className="btn btn--ghost btn--sm" onClick={() => actions.updateEdge(edge.id, { provisional: false })}>Confirmar</button>
            </div>
          )}
          <label className="field">
            <span className="field__label">Palabra de enlace</span>
            <input type="text" value={edge.label} maxLength={300} onChange={(e) => actions.updateEdge(edge.id, { label: e.target.value })} />
          </label>
          <div className="source">
            <p className="field__label">Fragmento de origen{edge.sourcePage ? ` · página ${edge.sourcePage}` : ''}</p>
            {edge.sourceText
              ? <blockquote>{edge.sourceText}</blockquote>
              : <p className="muted">{edge.kind === 'hierarchy' ? 'Sale de la estructura del documento (títulos y subtítulos).' : 'Sin fragmento asociado.'}</p>}
          </div>
          {edge.kind === 'hierarchy'
            ? <p className="panel__tip">Las relaciones jerárquicas siguen al concepto padre: cambia el padre o elimina el concepto para modificarlas.</p>
            : (
              <div className="panel__actions">
                <button className="btn btn--danger-ghost" onClick={() => actions.deleteEdge(edge.id)}>
                  <Icon name="trash" /> Eliminar relación
                </button>
              </div>
            )}
        </div>
      )
    }
  }

  const review = map.nodes.filter((n) => n.provisional)
  return (
    <div className="panel__body">
      <p className="panel__kind">Información</p>
      <p>Selecciona un concepto o una relación para ver de qué parte del PDF salió y editarlo.</p>
      <ul className="tips">
        <li>El botón «+N» de un concepto despliega sus ramas.</li>
        <li>Arrastra el fondo para desplazarte y usa la rueda para acercar o alejar.</li>
        <li>Los cambios no se guardan hasta pulsar «Guardar cambios».</li>
      </ul>
      {map.warnings.length > 0 && (
        <div className="warnings">
          <p className="field__label">Avisos del procesamiento</p>
          <ul>{map.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
      )}
      {review.length > 0 && (
        <div className="links">
          <p className="field__label">Por revisar ({countProvisional(map)})</p>
          <ul>
            {review.slice(0, 12).map((n) => (
              <li key={n.id}><button className="linkbtn" onClick={() => actions.reveal(n.id)}>{short(n.label, 50)}</button></li>
            ))}
          </ul>
          {review.length > 12 && <p className="muted">y {review.length - 12} más…</p>}
        </div>
      )}
    </div>
  )
}
