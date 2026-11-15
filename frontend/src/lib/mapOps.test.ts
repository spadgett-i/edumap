import { describe, expect, it } from 'vitest'
import type { ConceptMap, MapNode } from '../types'
import {
  addChild, addRelation, deleteEdge, deleteNode, descendantsOf, layoutTree, nextId, reparent, validateMap,
} from './mapOps'

const node = (id: string, parentId: string | null): MapNode => ({
  id, label: id, description: '', sourcePage: 1, sourceText: 'x', parentId, kind: parentId ? 'section' : 'root', provisional: false,
})
const edge = (id: string, source: string, target: string, kind: 'hierarchy' | 'cross' = 'hierarchy') => ({
  id, source, target, label: 'contiene', kind, provisional: false, sourceText: '', sourcePage: null,
})
// raíz r -> a -> (a1, a2); r -> b
const base = (): ConceptMap => ({
  id: 'm', documentId: 'd', title: 'Mapa', warnings: [], meta: {},
  nodes: [node('r', null), node('a', 'r'), node('a1', 'a'), node('a2', 'a'), node('b', 'r')],
  edges: [edge('relacion-001', 'r', 'a'), edge('relacion-002', 'a', 'a1'), edge('relacion-003', 'a', 'a2'), edge('relacion-004', 'r', 'b')],
})

describe('mapOps', () => {
  it('calcula descendientes', () => {
    expect([...descendantsOf(base().nodes, 'a')].sort()).toEqual(['a1', 'a2'])
  })

  it('distribuye el árbol y oculta ramas contraídas', () => {
    const open = layoutTree(base().nodes, new Set())
    expect(open.visible.size).toBe(5)
    expect(open.positions.get('a1')!.x).toBe(open.positions.get('a')!.x + 400)
    const closed = layoutTree(base().nodes, new Set(['a']))
    expect([...closed.visible].sort()).toEqual(['a', 'b', 'r'])
  })

  it('genera ids consecutivos', () => {
    expect(nextId('concepto', ['concepto-009', 'concepto-002'])).toBe('concepto-010')
  })

  it('agrega un hijo con su relación jerárquica', () => {
    const { map, id } = addChild(base(), 'b')
    expect(map.nodes.find((n) => n.id === id)).toMatchObject({ parentId: 'b', kind: 'manual' })
    expect(map.edges.some((e) => e.source === 'b' && e.target === id && e.kind === 'hierarchy')).toBe(true)
  })

  it('elimina un concepto y reubica a sus hijos', () => {
    const map = deleteNode(base(), 'a')!
    expect(map.nodes.map((n) => n.id)).not.toContain('a')
    expect(map.nodes.find((n) => n.id === 'a1')!.parentId).toBe('r')
    expect(map.edges.some((e) => e.source === 'r' && e.target === 'a1' && e.kind === 'hierarchy')).toBe(true)
    expect(map.edges.every((e) => e.source !== 'a' && e.target !== 'a')).toBe(true)
  })

  it('no permite borrar la raíz', () => {
    expect(deleteNode(base(), 'r')).toBeNull()
  })

  it('cambia de padre sin crear ciclos', () => {
    const moved = reparent(base(), 'a1', 'b')!
    expect(moved.nodes.find((n) => n.id === 'a1')!.parentId).toBe('b')
    expect(moved.edges.find((e) => e.target === 'a1')!.source).toBe('b')
    expect(reparent(base(), 'a', 'a1')).toBeNull() // un hijo no puede ser padre de su ancestro
    expect(reparent(base(), 'a', 'a')).toBeNull()
  })

  it('agrega relaciones manuales sin duplicar y no borra jerárquicas', () => {
    const first = addRelation(base(), 'a1', 'b')!
    expect(first.map.edges[first.map.edges.length - 1]).toMatchObject({ kind: 'manual', source: 'a1', target: 'b' })
    expect(addRelation(first.map, 'b', 'a1')).toBeNull()
    expect(addRelation(base(), 'a', 'a')).toBeNull()
    expect(deleteEdge(first.map, first.id).edges).toHaveLength(4)
    expect(deleteEdge(base(), 'relacion-001').edges).toHaveLength(4) // jerárquica: intacta
  })

  it('valida textos vacíos', () => {
    const map = base()
    map.nodes[1].label = '  '
    expect(validateMap(map)).toEqual(['Hay 1 concepto(s) sin texto.'])
  })
})
