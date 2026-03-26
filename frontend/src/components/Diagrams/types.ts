import type { FlowNodeType } from '../../types'

export interface DiagramNodeData {
  nodeType: FlowNodeType
  label: string
  description: string
  file?: string
  lineStart?: number
  lineEnd?: number
  symbol?: string
  expandable?: boolean
  selected?: boolean
}
