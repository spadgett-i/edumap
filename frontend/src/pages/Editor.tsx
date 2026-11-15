import {
  Background, MarkerType, ReactFlow, ReactFlowProvider, useReactFlow,
  type Connection, type Edge, type NodeTypes,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { ConceptNode, type ConceptFlowNode } from '../components/ConceptNode'
import { Icon } from '../components/Icon'
import { NodePanel, type PanelActions, type Selection } from '../components/NodePanel'
import { Shell } from '../components/Shell'
import {
  addChild, addRelation, childrenIndex, deleteEdge, deleteNode, layoutTree, reparent, updateEdge, updateNode,
  validateMap,
} from '../lib/mapOps'
import { navigate, paths } from '../lib/router'
import type { ConceptMap, EdgeKind } from '../types'

const nodeTypes: NodeTypes = { concept: ConceptNode }
const NAVY = '#03215A'
const RED = '#A7152E'
const EDGE_COLOR: Record<EdgeKind, string> = {
  hierarchy: 'rgba(3,33,90,0.5)', explicit: NAVY, cross: 'rgba(3,33,90,0.6)', manual: RED,
}
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
const animation = () => (reducedMotion() ? 0 : 250)

/** Con mapas grandes se muestran de entrada solo los dos primeros niveles. */
function initialCollapsed(map: ConceptMap): Set<string> {
  if (map.nodes.length <= 60) return new Set()
  const byId = new Map(map.nodes.map((n) => [n.id, n]))
  const depth = (id: string): number => { let d = 0; let cur = byId.get(id); while (cur?.parentId) { d++; cur = byId.get(cur.parentId) } return d }
  const kids = childrenIndex(map.nodes)
  return new Set(map.nodes.filter((n) => kids.has(n.id) && depth(n.id) >= 2).map((n) => n.id))
}

export function EditorPage({ projectId }: { projectId: string }) {
  const [map, setMap] = useState<ConceptMap | null>(null)
  const [error, setError] = useState<string | null>(null)
  const saved = useRef('')
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  useEffect(() => {
    setMap(null)
    api.getMap(projectId)
      .then((m) => { setMap(m); saved.current = JSON.stringify(m); setCollapsed(initialCollapsed(m)) })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'No se pudo abrir el mapa.'))
  }, [projectId])

  if (error) {
    return (
      <Shell active="library" title="Mapa conceptual">
        <div className="narrow">
          <div className="alert alert--error" role="alert"><Icon name="alert" /> <span>{error}</span></div>
          <a className="btn btn--primary" href={paths.library}>Volver a los documentos</a>
        </div>
      </Shell>
    )
  }
  if (!map) {
    return <Shell active="library" title="Abriendo mapa…"><div className="narrow"><p className="lead">Cargando el mapa conceptual…</p></div></Shell>
  }
  return (
    <ReactFlowProvider>
      <EditorInner projectId={projectId} map={map} setMap={setMap} saved={saved} collapsed={collapsed} setCollapsed={setCollapsed} />
    </ReactFlowProvider>
  )
}

function EditorInner({ projectId, map, setMap, saved, collapsed, setCollapsed }: {
  projectId: string
  map: ConceptMap
  setMap: (m: ConceptMap) => void
  saved: React.MutableRefObject<string>
  collapsed: Set<string>
  setCollapsed: (s: Set<string>) => void
}) {
  const flow = useReactFlow()
  const [selection, setSelection] = useState<Selection>(null)
  const [status, setStatus] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [focusId, setFocusId] = useState<string | null>(null)
  const [fitTick, setFitTick] = useState(0)

  const dirty = useMemo(() => JSON.stringify(map) !== saved.current, [map, saved])
  const problems = useMemo(() => validateMap(map), [map])

  // Aviso del navegador si se cierra la pestaña con cambios sin guardar
  useEffect(() => {
    if (!dirty) return
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault() }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

  const toggle = useCallback((id: string) => {
    setCollapsed((() => {
      const next = new Set(collapsed)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })())
  }, [collapsed, setCollapsed])

  const kids = useMemo(() => childrenIndex(map.nodes), [map.nodes])
  const { positions, visible } = useMemo(() => layoutTree(map.nodes, collapsed), [map.nodes, collapsed])

  const nodes: ConceptFlowNode[] = useMemo(
    () => map.nodes.filter((n) => visible.has(n.id)).map((n) => ({
      id: n.id,
      type: 'concept' as const,
      position: positions.get(n.id)!,
      draggable: false,
      selected: false,
      data: {
        label: n.label || '(sin texto)', kind: n.kind, provisional: n.provisional,
        childCount: kids.get(n.id)?.length ?? 0, collapsed: collapsed.has(n.id),
        isSelected: selection?.type === 'node' && selection.id === n.id, onToggle: toggle,
      },
    })),
    [map.nodes, visible, positions, kids, collapsed, selection, toggle],
  )

  const edges: Edge[] = useMemo(
    () => map.edges.filter((e) => visible.has(e.source) && visible.has(e.target)).map((e) => {
      const isSel = selection?.type === 'edge' && selection.id === e.id
      const color = isSel ? RED : EDGE_COLOR[e.kind]
      return {
        id: e.id, source: e.source, target: e.target, label: e.label, selected: isSel,
        className: `edge-${e.kind}${e.provisional ? ' edge-provisional' : ''}${isSel ? ' edge-selected' : ''}`,
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color },
        labelStyle: { fill: isSel ? RED : NAVY, fontSize: 12, fontWeight: 500 },
        labelBgStyle: { fill: '#FFFFFF', fillOpacity: 0.94 },
        labelBgPadding: [6, 3] as [number, number],
        labelBgBorderRadius: 4,
        interactionWidth: 24,
      }
    }),
    [map.edges, visible, selection],
  )

  // Enfocar un concepto concreto (p. ej. desde la lista «Por revisar»)
  useEffect(() => {
    if (!focusId) return
    const t = window.setTimeout(() => {
      flow.fitView({ nodes: [{ id: focusId }], padding: 1.2, maxZoom: 1, duration: animation() })
      setFocusId(null)
    }, 30)
    return () => window.clearTimeout(t)
  }, [focusId, flow])

  // Encuadre tras «Expandir todo» / «Contraer todo»
  useEffect(() => {
    if (fitTick === 0) return
    const t = window.setTimeout(() => flow.fitView({ padding: 0.2, duration: animation() }), 30)
    return () => window.clearTimeout(t)
  }, [fitTick, flow])

  const edit = (next: ConceptMap | null) => { if (next) { setMap(next); setStatus(null) } }

  const actions: PanelActions = {
    select: setSelection,
    reveal: (id) => {
      const byId = new Map(map.nodes.map((n) => [n.id, n]))
      const next = new Set(collapsed)
      for (let cur = byId.get(id)?.parentId; cur; cur = byId.get(cur)?.parentId) next.delete(cur)
      setCollapsed(next)
      setSelection({ type: 'node', id })
      setFocusId(id)
    },
    updateNode: (id, patch) => {
      let next = updateNode(map, id, patch)
      const node = map.nodes.find((n) => n.id === id)
      if (node?.parentId === null && patch.label !== undefined) next = { ...next, title: patch.label }
      edit(next)
    },
    updateEdge: (id, patch) => edit(updateEdge(map, id, patch)),
    setParent: (id, parentId) => {
      const next = reparent(map, id, parentId)
      if (next) {
        const open = new Set(collapsed)
        open.delete(parentId)
        setCollapsed(open)
      }
      edit(next)
    },
    addChild: (parentId) => {
      const { map: next, id } = addChild(map, parentId)
      const open = new Set(collapsed)
      open.delete(parentId)
      setCollapsed(open)
      edit(next)
      setSelection({ type: 'node', id })
      setFocusId(id)
    },
    deleteNode: (id) => {
      edit(deleteNode(map, id))
      setSelection(null)
    },
    deleteEdge: (id) => {
      edit(deleteEdge(map, id))
      setSelection(null)
    },
  }

  const onConnect = (c: Connection) => {
    if (!c.source || !c.target) return
    const result = addRelation(map, c.source, c.target)
    if (!result) {
      setStatus({ kind: 'error', text: 'Esos dos conceptos ya están relacionados.' })
      return
    }
    setMap(result.map)
    setStatus(null)
    setSelection({ type: 'edge', id: result.id })
  }

  const save = async () => {
    if (problems.length) { setStatus({ kind: 'error', text: problems.join(' ') }); return }
    setSaving(true)
    try {
      const result = await api.saveMap(projectId, map)
      saved.current = JSON.stringify(result)
      setMap(result)
      setStatus({ kind: 'ok', text: 'Cambios guardados en este equipo.' })
    } catch (e) {
      setStatus({ kind: 'error', text: e instanceof ApiError ? e.message : 'No se pudo guardar.' })
    } finally {
      setSaving(false)
    }
  }

  const reset = async () => {
    if (!window.confirm('¿Restablecer el mapa generado originalmente? Se perderán todas tus ediciones guardadas.')) return
    try {
      const original = await api.resetMap(projectId)
      saved.current = JSON.stringify(original)
      setMap(original)
      setCollapsed(initialCollapsed(original))
      setSelection(null)
      setStatus({ kind: 'ok', text: 'Se restableció el mapa generado originalmente.' })
      setFitTick((t) => t + 1)
    } catch (e) {
      setStatus({ kind: 'error', text: e instanceof ApiError ? e.message : 'No se pudo restablecer.' })
    }
  }

  const back = () => {
    if (dirty && !window.confirm('Tienes cambios sin guardar. ¿Salir de todos modos?')) return
    navigate(paths.library)
  }

  const goQuiz = () => {
    if (dirty && !window.confirm('Tienes cambios sin guardar. ¿Ir al cuestionario de todos modos?')) return
    navigate(paths.quiz(projectId))
  }

  const expandAll = () => { setCollapsed(new Set()); setFitTick((t) => t + 1) }
  const collapseAll = () => {
    setCollapsed(new Set(map.nodes.filter((n) => kids.has(n.id) && n.parentId !== null).map((n) => n.id)))
    setFitTick((t) => t + 1)
  }

  return (
    <Shell active="library" flush title={map.title}
      actions={
        <>
          <button className="btn btn--secondary" onClick={back}><Icon name="back" /> Volver a los documentos</button>
          <button className="btn btn--secondary" onClick={goQuiz}><Icon name="check" /> Cuestionario</button>
          <button className="btn btn--secondary" onClick={reset}><Icon name="reset" /> Restablecer</button>
          <button className="btn btn--primary" onClick={save} disabled={!dirty || saving}>
            <Icon name="save" /> {saving ? 'Guardando…' : 'Guardar cambios'}
          </button>
        </>
      }>
      <div className="editor">
        <section className="canvas" aria-label="Mapa conceptual">
          <div className="toolbar" role="toolbar" aria-label="Herramientas del mapa">
            <button className="tool" onClick={() => flow.zoomIn({ duration: animation() })}><Icon name="plus" /> Acercar</button>
            <button className="tool" onClick={() => flow.zoomOut({ duration: animation() })}><Icon name="minus" /> Alejar</button>
            <button className="tool" onClick={() => flow.fitView({ padding: 0.2, duration: animation() })}><Icon name="fit" /> Centrar</button>
            <span className="toolbar__sep" aria-hidden="true" />
            <button className="tool" onClick={expandAll}><Icon name="expand" /> Expandir todo</button>
            <button className="tool" onClick={collapseAll}><Icon name="collapse" /> Contraer todo</button>
          </div>

          <div className="status" role="status" aria-live="polite">
            {status && <span className={`status__msg status__msg--${status.kind}`}>{status.text}</span>}
            {!status && dirty && <span className="status__msg">Hay cambios sin guardar.</span>}
          </div>

          <ReactFlow
            nodes={nodes} edges={edges} nodeTypes={nodeTypes}
            nodesDraggable={false} deleteKeyCode={null} selectionKeyCode={null}
            minZoom={0.1} maxZoom={2} fitView fitViewOptions={{ padding: 0.2 }}
            onNodeClick={(_, n) => setSelection({ type: 'node', id: n.id })}
            onEdgeClick={(_, e) => setSelection({ type: 'edge', id: e.id })}
            onPaneClick={() => setSelection(null)}
            onConnect={onConnect}
          >
            <Background gap={24} size={1} color="rgba(3,33,90,0.12)" />
          </ReactFlow>

          <ul className="legend" aria-label="Leyenda">
            <li><i className="lg lg--root" /> Concepto central</li>
            <li><i className="lg lg--section" /> Sección</li>
            <li><i className="lg lg--concept" /> Concepto</li>
            <li><i className="lg lg--flag" /> Por revisar</li>
            <li><i className="lg lg--edge" /> Relación explícita</li>
            <li><i className="lg lg--edge-dash" /> Relación provisional</li>
          </ul>
        </section>

        <aside className="panel" aria-label="Propiedades del concepto seleccionado">
          <NodePanel map={map} selection={selection} actions={actions} />
        </aside>
      </div>
    </Shell>
  )
}
