import type {
  ProjectUploadResponse,
  WikiDocument,
  WikiGenerateResponse,
  WikiTaskStatusResponse,
} from '../types/wiki'

async function asJson<T>(res: Response, fallbackError: string): Promise<T> {
  if (!res.ok) {
    let detail = fallbackError
    try {
      const err = await res.json()
      detail = err.detail || fallbackError
    } catch {
      // ignore
    }
    throw new Error(detail)
  }
  return res.json()
}

export async function uploadProject(files: FileList | { path: string; file: File }[]): Promise<ProjectUploadResponse> {
  const form = new FormData()
  if (files instanceof FileList) {
    for (const f of Array.from(files)) {
      form.append('files', f, f.webkitRelativePath || f.name)
    }
  } else {
    for (const { path, file } of files) {
      form.append('files', file, path)
    }
  }
  const res = await fetch('/api/file/upload-project', { method: 'POST', body: form })
  return asJson<ProjectUploadResponse>(res, '项目上传失败')
}

export async function startWikiGeneration(projectName?: string): Promise<WikiGenerateResponse> {
  const res = await fetch('/api/wiki/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_name: projectName ?? null }),
  })
  return asJson<WikiGenerateResponse>(res, '启动 Wiki 生成失败')
}

export async function getWikiTaskStatus(taskId: string): Promise<WikiTaskStatusResponse> {
  const res = await fetch(`/api/wiki/status/${encodeURIComponent(taskId)}`)
  return asJson<WikiTaskStatusResponse>(res, '查询任务状态失败')
}

export async function getWikiDocument(projectName: string): Promise<WikiDocument> {
  const res = await fetch(`/api/wiki/${encodeURIComponent(projectName)}`)
  return asJson<WikiDocument>(res, '获取 Wiki 文档失败')
}

export async function getPersistedProject(projectName: string): Promise<ProjectUploadResponse> {
  const res = await fetch(`/api/file/project/${encodeURIComponent(projectName)}`)
  return asJson<ProjectUploadResponse>(res, '加载项目源码失败')
}

/**
 * 触发浏览器下载整份 Wiki 的 Markdown 版本。
 */
export async function downloadWikiMarkdown(projectName: string): Promise<void> {
  const res = await fetch(`/api/wiki/${encodeURIComponent(projectName)}/export`)
  if (!res.ok) {
    let detail = '导出 Markdown 失败'
    try {
      const err = await res.json()
      detail = err.detail || detail
    } catch {
      // ignore
    }
    throw new Error(detail)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  // 优先用 Content-Disposition 的文件名；fallback 到 <project>.md
  const disposition = res.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="([^"]+)"/)
  a.download = match ? match[1] : `${projectName}.md`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/**
 * 轮询任务状态直至终止（done / failed），每 2s 一次。
 * onUpdate 可选：用于把中间状态反馈给 UI。
 *
 * 对瞬时错误（网络抖动、后端热重启）做容错：连续 N 次失败才真正抛出。
 */
export async function pollWikiStatus(
  taskId: string,
  onUpdate?: (status: WikiTaskStatusResponse) => void,
  intervalMs = 2000,
  maxConsecutiveErrors = 5,
): Promise<WikiTaskStatusResponse> {
  let consecutiveErrors = 0
  let lastError: unknown = null
  while (true) {
    try {
      const status = await getWikiTaskStatus(taskId)
      consecutiveErrors = 0
      onUpdate?.(status)
      if (status.status === 'done' || status.status === 'failed') {
        return status
      }
    } catch (e) {
      consecutiveErrors += 1
      lastError = e
      console.warn(
        `[pollWikiStatus] 轮询错误 ${consecutiveErrors}/${maxConsecutiveErrors}:`,
        e,
      )
      if (consecutiveErrors >= maxConsecutiveErrors) {
        throw lastError instanceof Error
          ? lastError
          : new Error('轮询 Wiki 任务状态失败')
      }
    }
    await new Promise((r) => setTimeout(r, intervalMs))
  }
}
