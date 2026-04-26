export type PageType = 'overview' | 'category' | 'chapter' | 'topic' | 'module'
export type PageStatus = 'generated'

export interface CodeRef {
  file: string
  start_line: number
  end_line: number
  symbol?: string | null
}

export interface ModuleInfo {
  files: string[]   // 文件路径列表
}

export interface PageMetadata {
  outgoing_links: string[]
  code_refs: Record<string, CodeRef>
  module_info?: ModuleInfo | null
  brief?: string | null
}

export interface WikiPage {
  id: string
  type: PageType
  title: string
  path?: string | null
  status: PageStatus
  content_md: string | null
  metadata: PageMetadata
}

export interface WikiIndexNode {
  title: string
  children: string[]
}

export interface WikiIndex {
  root: string
  tree: Record<string, WikiIndexNode>
}

export interface WikiDocument {
  project_name: string
  project_hash: string
  generated_at: string
  pages: WikiPage[]
  index: WikiIndex
}

export interface ProjectFile {
  path: string
  content: string
  line_count: number
}

export interface ProjectUploadResponse {
  project_name: string
  files: ProjectFile[]
}

export interface WikiGenerateResponse {
  task_id: string
  project_name: string
}

export type WikiTaskStatus = 'pending' | 'running' | 'done' | 'failed'

export interface WikiTaskStatusResponse {
  task_id: string
  status: WikiTaskStatus
  project_name: string
  message?: string | null
  created_at: string
}
