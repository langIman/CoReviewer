import { useState, useEffect, useCallback } from 'react'
import UploadBar from './components/UploadBar'
import CodeView from './components/CodeView/CodeView'
import ActionBar from './components/ActionBar'
import AIPanel from './components/AIPanel/AIPanel'
import FileTree from './components/FileTree/FileTree'
import { useReviewStore } from './store/useReviewStore'
import { uploadFile, uploadProject, generateProjectSummary } from './services/api'
import { useLanguage } from './i18n/LanguageContext'

export default function App() {
  const projectMode = useReviewStore((s) => s.projectMode)
  const setFile = useReviewStore((s) => s.setFile)
  const setProject = useReviewStore((s) => s.setProject)
  const summaryLoading = useReviewStore((s) => s.summaryLoading)
  const { t } = useLanguage()

  /** 上传项目后自动生成摘要 */
  const handleProjectLoaded = useCallback(async () => {
    const { setSummaryLoading, setSummaryReady } = useReviewStore.getState()
    try {
      await generateProjectSummary()
      setSummaryReady(true)
    } catch {
      // 摘要失败不阻塞使用，但标记完成
      setSummaryReady(true)
    } finally {
      setSummaryLoading(false)
    }
  }, [])

  const [dragging, setDragging] = useState(false)
  const [dragCounter, setDragCounter] = useState(0)

  // 全局阻止浏览器默认拖放行为（防止打开文件）
  useEffect(() => {
    const prevent = (e: DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
    }
    document.addEventListener('dragover', prevent)
    document.addEventListener('drop', prevent)
    return () => {
      document.removeEventListener('dragover', prevent)
      document.removeEventListener('drop', prevent)
    }
  }, [])

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragCounter((c) => c + 1)
    setDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragCounter((c) => {
      const next = c - 1
      if (next <= 0) setDragging(false)
      return Math.max(0, next)
    })
  }, [])

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      setDragCounter(0)

      const items = e.dataTransfer.items
      if (!items || items.length === 0) return

      // 检测是否拖入了文件夹（通过 webkitGetAsEntry）
      const firstEntry = items[0].webkitGetAsEntry?.()
      if (firstEntry?.isDirectory) {
        // 文件夹拖入：收集所有 .py 文件
        const files = await collectFilesFromDrop(items)
        if (files.length === 0) {
          alert(t('upload.noFiles'))
          return
        }
        try {
          const form = new FormData()
          for (const { path, file } of files) {
            form.append('files', file, path)
          }
          const res = await fetch('/api/file/upload-project', { method: 'POST', body: form })
          if (!res.ok) {
            const err = await res.json()
            throw new Error(err.detail || t('upload.projectFailed'))
          }
          const data = await res.json()
          setProject(data)
          handleProjectLoaded()
        } catch (err: unknown) {
          alert(err instanceof Error ? err.message : t('upload.projectFailed'))
        }
      } else {
        // 单文件拖入
        const file = e.dataTransfer.files[0]
        if (!file) return
        try {
          const data = await uploadFile(file)
          setFile(data)
        } catch (err: unknown) {
          alert(err instanceof Error ? err.message : t('upload.failed'))
        }
      }
    },
    [setFile, setProject]
  )

  return (
    <div
      className="flex flex-col h-screen bg-white dark:bg-gray-900 relative"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
    >
      <UploadBar />
      <div className="flex flex-1 overflow-hidden">
        {projectMode && (
          <div className="w-56 flex-shrink-0 border-r border-gray-200 dark:border-gray-700 overflow-auto bg-gray-50 dark:bg-gray-800">
            <FileTree />
          </div>
        )}
        <div className="flex flex-col flex-1 border-r border-gray-200 dark:border-gray-700 min-w-0">
          <CodeView />
          <ActionBar />
        </div>
        <div className="flex-1 min-w-0">
          <AIPanel />
        </div>
      </div>

      {/* 全屏拖放遮罩 */}
      {dragging && (
        <div className="absolute inset-0 z-50 bg-blue-500/10 border-4 border-dashed border-blue-400 flex items-center justify-center pointer-events-none">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg px-8 py-6 text-center">
            <div className="text-3xl mb-2">📁</div>
            <p className="text-lg font-medium text-gray-700 dark:text-gray-200">{t('drop.title')}</p>
            <p className="text-sm text-gray-400 mt-1">{t('drop.hint')}</p>
          </div>
        </div>
      )}
    </div>
  )
}

/** 递归收集拖入文件夹中的所有文件 */
async function collectFilesFromDrop(
  items: DataTransferItemList
): Promise<{ path: string; file: File }[]> {
  const results: { path: string; file: File }[] = []

  async function readEntry(entry: FileSystemEntry, basePath: string) {
    if (entry.isFile) {
      const file = await new Promise<File>((resolve) =>
        (entry as FileSystemFileEntry).file(resolve)
      )
      results.push({ path: basePath + entry.name, file })
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader()
      const entries = await new Promise<FileSystemEntry[]>((resolve) =>
        reader.readEntries(resolve)
      )
      for (const child of entries) {
        await readEntry(child, basePath + entry.name + '/')
      }
    }
  }

  for (let i = 0; i < items.length; i++) {
    const entry = items[i].webkitGetAsEntry?.()
    if (entry) {
      await readEntry(entry, '')
    }
  }

  return results
}
