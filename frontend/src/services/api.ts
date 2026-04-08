import type { FileData, ProjectData, FlowData } from '../types'

export async function uploadFile(file: File): Promise<FileData> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch('/api/file/upload', { method: 'POST', body: form })
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
  const res = await fetch('/api/file/upload-project', { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Project upload failed')
  }
  return res.json()
}

/** Expand a function's internal logic via LLM */
export async function analyzeDetail(qualifiedName: string): Promise<FlowData> {
  const res = await fetch('/api/graph/detail', {
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
  const res = await fetch('/api/graph/overview', { method: 'POST' })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Overview generation failed')
  }
  return res.json()
}

export async function generateHierarchicalSummary(): Promise<{
  project_name: string
  project_summary: string
}> {
  const res = await fetch('/api/summary/generate', { method: 'POST' })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Hierarchical summary generation failed')
  }
  return res.json()
}

export async function splitModules(): Promise<{ modules: { name: string; description: string; paths: string[] }[] }> {
  const res = await fetch('/api/module/split', { method: 'POST' })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Module split failed')
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
