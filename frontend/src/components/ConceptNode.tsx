import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import type { NodeKind } from '../types'

export type ConceptNodeData = {
  label: string
  kind: NodeKind
  provisional: boolean
  childCount: number
  collapsed: boolean
  isSelected: boolean
  onToggle: (id: string) => void
}
export type ConceptFlowNode = Node<ConceptNodeData, 'concept'>

export function ConceptNode({ id, data }: NodeProps<ConceptFlowNode>) {
  const cls = ['cnode', `cnode--${data.kind}`, data.isSelected && 'is-selected', data.provisional && 'is-provisional']
    .filter(Boolean).join(' ')
  return (
    <div className={cls}>
      <Handle type="target" position={Position.Left} />
      <div className="cnode__label">{data.label}</div>
      {data.provisional && <span className="cnode__flag">Revisar</span>}
      {data.childCount > 0 && (
        <button
          type="button"
          className="cnode__toggle nodrag nopan"
          aria-expanded={!data.collapsed}
          aria-label={`${data.collapsed ? 'Expandir' : 'Contraer'} ${data.childCount} concepto(s) de «${data.label}»`}
          onClick={(e) => { e.stopPropagation(); data.onToggle(id) }}
        >
          {data.collapsed ? `+${data.childCount}` : '−'}
        </button>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  )
}
