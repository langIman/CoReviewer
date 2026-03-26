export interface FileData {
  filename: string
  content: string
  line_count: number
}

export interface Selection {
  startLine: number
  endLine: number
  selectedText: string
}

export interface ReviewResponse {
  id: string
  startLine: number
  endLine: number
  content: string
  action: string
  loading: boolean
  timestamp: number
}

export interface ProjectFile {
  path: string
  content: string
  line_count: number
}

export interface ProjectData {
  project_name: string
  files: ProjectFile[]
}

export type FlowNodeType = 'start' | 'end' | 'process' | 'decision'

export interface FlowNode {
  id: string
  type: FlowNodeType
  label: string
  description: string
  file?: string
  lineStart?: number
  lineEnd?: number
  symbol?: string
  expandable?: boolean
}

export interface FlowEdge {
  source: string
  target: string
  label?: string
}

export interface FlowData {
  nodes: FlowNode[]
  edges: FlowEdge[]
}

export interface FileTreeNode {
  name: string
  path: string
  type: 'file' | 'directory'
  children?: FileTreeNode[]
}
