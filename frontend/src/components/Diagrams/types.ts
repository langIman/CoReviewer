import type { FlowNodeType } from '../../types'

export interface DiagramNodeData {
  nodeType: FlowNodeType
  label: string
  description: string
  file?: string
  line?: number
  expandable?: boolean
  selected?: boolean
}
