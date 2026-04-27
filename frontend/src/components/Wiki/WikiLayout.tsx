import { useState } from 'react'
import { useWikiStore } from '../../store/useWikiStore'
import { useQAStore } from '../../store/useQAStore'
import { downloadWikiMarkdown } from '../../services/api'
import FloatingCodeWindow from '../CodeDrawer/FloatingCodeWindow'
import QADrawer from '../QA/QADrawer'
import QAHandle from '../QA/QAHandle'
import ThemeToggle from '../common/ThemeToggle'
import NavTree from './NavTree'
import WikiPageView from './WikiPageView'

function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000))
  const m = Math.floor(total / 60)
  const s = total % 60
  if (m === 0) return `${s}s`
  return `${m}m ${String(s).padStart(2, '0')}s`
}

export default function WikiLayout() {
  const projectName = useWikiStore((s) => s.projectName)
  const lastGenerationDurationMs = useWikiStore((s) => s.lastGenerationDurationMs)
  const reset = useWikiStore((s) => s.reset)
  const resetQA = useQAStore((s) => s.reset)
  const [exporting, setExporting] = useState(false)

  const handleReset = () => {
    resetQA()
    reset()
  }

  const handleExport = async () => {
    if (!projectName || exporting) return
    try {
      setExporting(true)
      await downloadWikiMarkdown(projectName)
    } catch (e) {
      console.error('[export] 导出失败:', e)
      alert(e instanceof Error ? e.message : '导出失败')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="flex flex-col h-screen bg-white dark:bg-gray-900">
      <header className="flex items-center px-4 py-2 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 gap-3 flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-base">📖</span>
          <span className="font-semibold text-gray-800 dark:text-gray-100">CoReviewer</span>
          {projectName && (
            <>
              <span className="text-gray-300 dark:text-gray-600">/</span>
              <code className="font-mono text-sm text-gray-600 dark:text-gray-400">
                {projectName}
              </code>
            </>
          )}
          {lastGenerationDurationMs !== null && (
            <span
              className="ml-1 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
              title="本次生成耗时"
            >
              ⏱ 生成耗时 {formatDuration(lastGenerationDurationMs)}
            </span>
          )}
        </div>

        <div className="h-5 w-px bg-gray-200 dark:bg-gray-700 mx-1" />

        <nav className="flex items-center gap-1">
          <button
            className="px-3 py-1 text-sm rounded bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-medium"
            aria-current="page"
          >
            📖 Wiki
          </button>
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => void handleExport()}
            disabled={!projectName || exporting}
            className="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
            title="将整份 Wiki 导出为单个 Markdown 文件"
          >
            {exporting ? '导出中...' : '📥 导出 Markdown'}
          </button>
          <button
            onClick={handleReset}
            className="text-xs text-gray-500 dark:text-gray-400 hover:text-red-500 dark:hover:text-red-400"
            title="返回上传视图"
          >
            重新上传
          </button>
          <div className="h-4 w-px bg-gray-200 dark:bg-gray-700" />
          <ThemeToggle />
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-64 flex-shrink-0">
          <NavTree />
        </aside>
        <main className="flex-1 flex flex-col min-w-0">
          <WikiPageView />
        </main>
        <QADrawer />
      </div>

      <QAHandle />
      <FloatingCodeWindow />
    </div>
  )
}
