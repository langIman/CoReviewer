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
  line?: number
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
