import type {
  Conversation,
  ConversationDetail,
  QARequest,
  SSEEvent,
} from '../types/qa'

async function asJson<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) {
    let detail = fallback
    try {
      const err = await res.json()
      detail = err.detail || fallback
    } catch {
      // ignore
    }
    throw new Error(detail)
  }
  return res.json()
}

export async function listConversations(projectName: string): Promise<Conversation[]> {
  const res = await fetch(
    `/api/qa/conversations?project_name=${encodeURIComponent(projectName)}`,
  )
  return asJson<Conversation[]>(res, '获取会话列表失败')
}

export async function getConversation(conversationId: string): Promise<ConversationDetail> {
  const res = await fetch(`/api/qa/conversations/${encodeURIComponent(conversationId)}`)
  return asJson<ConversationDetail>(res, '获取会话详情失败')
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const res = await fetch(`/api/qa/conversations/${encodeURIComponent(conversationId)}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    throw new Error('删除会话失败')
  }
}

export async function* streamAsk(
  req: QARequest,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const res = await fetch('/api/qa/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(req),
    signal,
  })
  if (!res.ok || !res.body) {
    let detail = '问答请求失败'
    try {
      const err = await res.json()
      detail = err.detail || detail
    } catch {
      // ignore
    }
    throw new Error(detail)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let sep: number
      while ((sep = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)
        const parsed = parseFrame(frame)
        if (parsed) yield parsed
      }
    }
    if (buffer.trim()) {
      const parsed = parseFrame(buffer)
      if (parsed) yield parsed
    }
  } finally {
    try {
      reader.releaseLock()
    } catch {
      // ignore
    }
  }
}

function parseFrame(frame: string): SSEEvent | null {
  let eventName = ''
  const dataLines: string[] = []
  for (const raw of frame.split('\n')) {
    const line = raw.replace(/\r$/, '')
    if (!line || line.startsWith(':')) continue
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }
  if (!eventName || dataLines.length === 0) return null
  try {
    const data = JSON.parse(dataLines.join('\n'))
    return { event: eventName, data } as SSEEvent
  } catch {
    return null
  }
}
