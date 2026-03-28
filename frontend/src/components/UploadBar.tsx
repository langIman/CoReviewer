import { useCallback, useRef, useState } from 'react'
import { useReviewStore } from '../store/useReviewStore'
import { uploadFile, uploadProject, generateProjectSummary, analyzeGraph, analyzeOverview } from '../services/api'
import { useLanguage } from '../i18n/LanguageContext'
import { useTheme } from '../i18n/ThemeContext'

export default function UploadBar() {
  const { file, projectMode, project, summaryLoading, summaryReady, setFile, setProject, clearProject } = useReviewStore()
  const { t, lang, toggleLang } = useLanguage()
  const { isDark, toggleTheme } = useTheme()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const [showMenu, setShowMenu] = useState(false)

  const handleUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0]
      if (!f) return
      try {
        const data = await uploadFile(f)
        setFile(data)
      } catch (err: unknown) {
        alert(err instanceof Error ? err.message : t('upload.failed'))
      }
      e.target.value = ''
    },
    [setFile, t]
  )

  const handleFolderUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (!files || files.length === 0) return
      try {
        const data = await uploadProject(files)
        setProject(data)
        const { setSummaryLoading, setSummaryReady } = useReviewStore.getState()
        generateProjectSummary()
          .then(() => setSummaryReady(true))
          .catch(() => setSummaryReady(true))
          .finally(() => setSummaryLoading(false))
      } catch (err: unknown) {
        alert(err instanceof Error ? err.message : t('upload.projectFailed'))
      }
      e.target.value = ''
    },
    [setProject, t]
  )

  const handleVisualize = useCallback(async () => {
    const { addResponse, updateResponseContent, setResponseDone } = useReviewStore.getState()
    const id = `viz-${Date.now()}`
    addResponse({
      id,
      startLine: 0,
      endLine: 0,
      content: '',
      action: 'visualize',
      loading: true,
      timestamp: Date.now(),
    })
    try {
      // Step 1: Show AST skeleton instantly (module-level call graph)
      analyzeGraph()
        .then((graphData) => {
          const skeleton = graphData.flow.module_level
          // Only show skeleton if LLM hasn't finished yet
          updateResponseContent(id, JSON.stringify(skeleton))
        })
        .catch(() => {
          // Skeleton failed — will wait for LLM overview
        })

      // Step 2: Generate semantic flowchart via LLM (same quality as before)
      // Uses AST skeleton as input instead of full code = fewer tokens
      const overviewData = await analyzeOverview()
      updateResponseContent(id, JSON.stringify(overviewData))
      setResponseDone(id)
    } catch (err: unknown) {
      updateResponseContent(id, '')
      setResponseDone(id)
      alert(err instanceof Error ? err.message : t('upload.failed'))
    }
  }, [t])

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
      <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">{t('app.title')}</span>
      <div className="h-4 w-px bg-gray-300 dark:bg-gray-600" />

      <div className="relative">
        <button
          className="px-3 py-1 text-sm text-white bg-blue-600 rounded hover:bg-blue-700 transition-colors"
          onClick={() => setShowMenu((v) => !v)}
          onBlur={() => setTimeout(() => setShowMenu(false), 150)}
        >
          {file || projectMode ? t('upload.switch') : t('upload.open')}
        </button>
        {showMenu && (
          <div className="absolute top-full left-0 mt-1 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg z-50 min-w-[160px]">
            <button
              className="w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600 rounded-t-lg"
              onMouseDown={() => { setShowMenu(false); fileInputRef.current?.click() }}
            >
              {t('upload.singleFile')}
            </button>
            <button
              className="w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600 rounded-b-lg"
              onMouseDown={() => { setShowMenu(false); folderInputRef.current?.click() }}
            >
              {t('upload.entireProject')}
            </button>
          </div>
        )}
      </div>

      <input ref={fileInputRef} type="file" accept=".py" className="hidden" onChange={handleUpload} />
      <input
        ref={folderInputRef}
        type="file"
        className="hidden"
        onChange={handleFolderUpload}
        {...({ webkitdirectory: '', directory: '' } as React.InputHTMLAttributes<HTMLInputElement>)}
      />

      {projectMode && summaryLoading && (
        <span className="text-xs text-amber-600 dark:text-amber-400 animate-pulse">
          {t('upload.analyzing')}
        </span>
      )}
      {projectMode && summaryReady && (
        <button
          className="px-2.5 py-1 text-xs font-medium text-white bg-purple-600 rounded hover:bg-purple-700 transition-colors"
          onClick={handleVisualize}
        >
          {t('visualize.button')}
        </button>
      )}
      {projectMode && (
        <button className="text-xs text-red-500 hover:text-red-700" onClick={clearProject}>
          {t('upload.clear')}
        </button>
      )}

      {!projectMode && !file && (
        <span className="text-xs text-gray-400">{t('upload.dragHint')}</span>
      )}

      {/* 主题切换 + 语言切换 */}
      <div className="ml-auto flex items-center gap-2 text-xs">
        <button
          onClick={toggleTheme}
          className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors text-gray-500 dark:text-gray-400"
          title={isDark ? 'Light mode' : 'Dark mode'}
        >
          {isDark ? (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
            </svg>
          )}
        </button>
        <div className="h-3 w-px bg-gray-300 dark:bg-gray-600" />
        <button
          onClick={lang === 'en' ? toggleLang : undefined}
          className={`px-1.5 py-0.5 rounded transition-colors ${
            lang === 'zh' ? 'text-blue-600 dark:text-blue-400 font-semibold' : 'text-gray-400 hover:text-gray-600 cursor-pointer'
          }`}
        >
          中文
        </button>
        <span className="text-gray-300 dark:text-gray-600">|</span>
        <button
          onClick={lang === 'zh' ? toggleLang : undefined}
          className={`px-1.5 py-0.5 rounded transition-colors ${
            lang === 'en' ? 'text-blue-600 dark:text-blue-400 font-semibold' : 'text-gray-400 hover:text-gray-600 cursor-pointer'
          }`}
        >
          EN
        </button>
      </div>
    </div>
  )
}
