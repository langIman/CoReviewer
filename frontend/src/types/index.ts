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
