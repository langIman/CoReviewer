import type { FileData, ProjectData, FlowData } from '../types'

export async function uploadFile(file: File): Promise<FileData> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch('/api/upload', { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Upload failed')
  }
  return res.json()
}

export async function uploadProject(files: FileList): Promise<ProjectData> {
  const form = new FormData()
  for (const file of Array.from(files)) {
    // webkitRelativePath 提供相对路径（含文件夹名）
    form.append('files', file, file.webkitRelativePath)
  }
  const res = await fetch('/api/upload-project', { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Project upload failed')
  }
  return res.json()
}

export async function generateProjectSummary(): Promise<string> {
  const res = await fetch('/api/project/summary', { method: 'POST' })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Summary generation failed')
  }
  const data = await res.json()
  return data.summary
}

export async function visualizeProject(): Promise<FlowData> {
  const res = await fetch('/api/visualize', { method: 'POST' })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Visualization failed')
  }
  return res.json()
}

export async function visualizeDetail(params: {
  label: string
  description: string
  file?: string
  symbol?: string
}): Promise<FlowData> {
  const res = await fetch('/api/visualize/detail', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Detail generation failed')
  }
  return res.json()
}

// --- AST-based analysis API (P1 + P2) ---

export interface AnalyzeGraphResponse {
  modules: Record<string, unknown>
  definitions: Record<string, unknown>
  edges: unknown[]
  flow: {
    module_level: FlowData
    function_level: Record<string, FlowData>
  }
}

export interface AnnotateResponse {
  status: 'ok' | 'fallback'
  error?: string
  annotations: Record<string, { label: string; description: string }>
}

/** Pure AST analysis — returns call graph + FlowData in milliseconds */
export async function analyzeGraph(): Promise<AnalyzeGraphResponse> {
  const res = await fetch('/api/analyze/graph', { method: 'POST' })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Graph analysis failed')
  }
  return res.json()
}

/** LLM semantic annotation — returns Chinese labels for each function */
export async function analyzeAnnotate(modules?: string[]): Promise<AnnotateResponse> {
  const res = await fetch('/api/analyze/annotate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(modules ? { modules } : {}),
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Annotation failed')
  }
  return res.json()
}

/** Expand a function's internal logic via LLM */
export async function analyzeDetail(qualifiedName: string): Promise<FlowData> {
  const res = await fetch('/api/analyze/detail', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ qualified_name: qualifiedName }),
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Detail analysis failed')
  }
  return res.json()
}

/** Semantic overview flowchart from AST skeleton + LLM (same format as old visualize) */
export async function analyzeOverview(): Promise<FlowData> {
  const res = await fetch('/api/analyze/overview', { method: 'POST' })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Overview generation failed')
  }
  return res.json()
}

export async function streamReview(
  params: {
    file_name: string
    full_content: string
    selected_code: string
    start_line: number
    end_line: number
    action: string
    project_mode?: boolean
  },
  onChunk: (text: string) => void,
  onDone: () => void
): Promise<void> {
  const res = await fetch('/api/review', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })

  if (!res.ok || !res.body) {
    const text = await res.text()
    onChunk(`Error: ${text}`)
    onDone()
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6)
      if (data.trim() === '[DONE]') {
        onDone()
        return
      }
      try {
        const text = JSON.parse(data)
        onChunk(text)
      } catch {
        // If not JSON-wrapped, use raw text
        if (data.trim()) onChunk(data)
      }
    }
  }
  onDone()
}
