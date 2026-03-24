import type { FileData } from '../types'

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

export async function streamReview(
  params: {
    file_name: string
    full_content: string
    selected_code: string
    start_line: number
    end_line: number
    action: string
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
