// Operaciones puras sobre el mapa (sin React): fáciles de probar y sin efectos secundarios.
import type { ConceptMap, MapEdge, MapNode } from '../types'

export const NODE_WIDTH = 240
export const COLUMN_WIDTH = 400 // ancho del nodo + espacio para la etiqueta de la relación
export const ROW_HEIGHT = 104

export type Positions = Map<string, { x: number; y: number }>

export function childrenIndex(nodes: MapNode[]): Map<string, string[]> {
  const index = new Map<string, string[]>()
  for (const n of nodes) {
    if (n.parentId) index.set(n.parentId, [...(index.get(n.parentId) ?? []), n.id])
  }
  return index
}

export function descendantsOf(nodes: MapNode[], id: string): Set<string> {
  const index = childrenIndex(nodes)
  const out = new Set<string>()
  const stack = [...(index.get(id) ?? [])]
  while (stack.length) {
    const cur = stack.pop()!
    if (out.has(cur)) continue
    out.add(cur)
    stack.push(...(index.get(cur) ?? []))
  }
  return out
}

/** Disposición de árbol de izquierda a derecha. Las ramas contraídas ocultan sus descendientes. */
export function layoutTree(nodes: MapNode[], collapsed: ReadonlySet<string>) {
  const index = childrenIndex(nodes)
  const ids = new Set(nodes.map((n) => n.id))
  const roots = nodes.filter((n) => n.parentId === null || !ids.has(n.parentId))
  const positions: Positions = new Map()
  let cursor = 0

  const place = (id: string, depth: number): number => {
    const kids = collapsed.has(id) ? [] : (index.get(id) ?? [])
    let y: number
    if (kids.length === 0) {
      y = cursor
      cursor += ROW_HEIGHT
    } else {
      const ys = kids.map((k) => place(k, depth + 1))
      y = (ys[0] + ys[ys.length - 1]) / 2
    }
    positions.set(id, { x: depth * COLUMN_WIDTH, y })
    return y
  }
  roots.forEach((r) => place(r.id, 0))
  return { positions, visible: new Set(positions.keys()) }
}

export function nextId(prefix: string, existing: Iterable<string>): string {
  let max = 0
  for (const id of existing) {
    const m = id.match(new RegExp(`^${prefix}-(\\d+)$`))
    if (m) max = Math.max(max, Number(m[1]))
  }
  return `${prefix}-${String(max + 1).padStart(3, '0')}`
}

const hierarchyEdge = (id: string, source: string, target: string, label = 'contiene', provisional = false): MapEdge => ({
  id, source, target, label, kind: 'hierarchy', provisional, sourceText: '', sourcePage: null,
})

export function hierarchyEdgeOf(map: ConceptMap, nodeId: string): MapEdge | undefined {
  return map.edges.find((e) => e.kind === 'hierarchy' && e.target === nodeId)
}

export function addChild(map: ConceptMap, parentId: string): { map: ConceptMap; id: string } {
  const id = nextId('concepto', map.nodes.map((n) => n.id))
  const node: MapNode = {
    id, label: 'Nuevo concepto', description: '', sourcePage: null, sourceText: '',
    parentId, kind: 'manual', provisional: false,
  }
  const edge = hierarchyEdge(nextId('relacion', map.edges.map((e) => e.id)), parentId, id)
  return { map: { ...map, nodes: [...map.nodes, node], edges: [...map.edges, edge] }, id }
}

/** Elimina un concepto; sus hijos pasan al padre del eliminado. No se puede borrar la raíz. */
export function deleteNode(map: ConceptMap, id: string): ConceptMap | null {
  const node = map.nodes.find((n) => n.id === id)
  if (!node || node.parentId === null) return null
  const children = map.nodes.filter((n) => n.parentId === id)
  const edges = map.edges.filter((e) => e.source !== id && e.target !== id)
  const used = edges.map((e) => e.id)
  for (const child of children) {
    const eid = nextId('relacion', used)
    used.push(eid)
    edges.push(hierarchyEdge(eid, node.parentId, child.id, 'contiene', true))
  }
  return {
    ...map,
    nodes: map.nodes.filter((n) => n.id !== id).map((n) => (n.parentId === id ? { ...n, parentId: node.parentId } : n)),
    edges,
  }
}

/** Cambia el padre de un concepto. Devuelve null si crearía un ciclo o si es la raíz. */
export function reparent(map: ConceptMap, id: string, newParentId: string): ConceptMap | null {
  const node = map.nodes.find((n) => n.id === id)
  if (!node || node.parentId === null || id === newParentId) return null
  if (descendantsOf(map.nodes, id).has(newParentId)) return null
  if (!map.nodes.some((n) => n.id === newParentId)) return null
  if (node.parentId === newParentId) return map
  const existing = hierarchyEdgeOf(map, id)
  const edges = existing
    ? map.edges.map((e) => (e.id === existing.id ? { ...e, source: newParentId } : e))
    : [...map.edges, hierarchyEdge(nextId('relacion', map.edges.map((e) => e.id)), newParentId, id)]
  return { ...map, nodes: map.nodes.map((n) => (n.id === id ? { ...n, parentId: newParentId } : n)), edges }
}

export function updateNode(map: ConceptMap, id: string, patch: Partial<MapNode>): ConceptMap {
  return { ...map, nodes: map.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)) }
}

export function updateEdge(map: ConceptMap, id: string, patch: Partial<MapEdge>): ConceptMap {
  return { ...map, edges: map.edges.map((e) => (e.id === id ? { ...e, ...patch } : e)) }
}

/** Crea una relación manual entre dos conceptos. Devuelve null si ya están conectados. */
export function addRelation(map: ConceptMap, source: string, target: string): { map: ConceptMap; id: string } | null {
  if (source === target) return null
  const connected = map.edges.some(
    (e) => (e.source === source && e.target === target) || (e.source === target && e.target === source),
  )
  if (connected) return null
  const id = nextId('relacion', map.edges.map((e) => e.id))
  const edge: MapEdge = {
    id, source, target, label: 'se relaciona con', kind: 'manual', provisional: false, sourceText: '', sourcePage: null,
  }
  return { map: { ...map, edges: [...map.edges, edge] }, id }
}

/** Las relaciones jerárquicas no se borran: se cambia el padre o se elimina el concepto. */
export function deleteEdge(map: ConceptMap, id: string): ConceptMap {
  return { ...map, edges: map.edges.filter((e) => !(e.id === id && e.kind !== 'hierarchy')) }
}

export function validateMap(map: ConceptMap): string[] {
  const problems: string[] = []
  if (!map.title.trim()) problems.push('El mapa necesita un título.')
  const empty = map.nodes.filter((n) => !n.label.trim())
  if (empty.length) problems.push(`Hay ${empty.length} concepto(s) sin texto.`)
  return problems
}

export function countProvisional(map: ConceptMap): number {
  return map.nodes.filter((n) => n.provisional).length + map.edges.filter((e) => e.provisional).length
}
