import { useReviewStore } from '../store/useReviewStore'
import { streamReview } from '../services/api'
import { useLanguage } from '../i18n/LanguageContext'

const ACTIONS = [
  { key: 'explain', labelKey: 'action.explain' },
] as const

export default function ActionBar() {
  const { file, selection, projectMode, summaryLoading } = useReviewStore()
  const { t } = useLanguage()
  const disabled = projectMode && summaryLoading

  if (!selection || !file) return null

  const handleAction = async (action: string) => {
    const { addResponse, updateResponseContent, setResponseDone } =
      useReviewStore.getState()

    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`

    addResponse({
      id,
      startLine: selection.startLine,
      endLine: selection.endLine,
      content: '',
      action,
      loading: true,
      timestamp: Date.now(),
    })

    const { projectMode } = useReviewStore.getState()

    let accumulated = ''
    await streamReview(
      {
        file_name: file.filename,
        full_content: file.content,
        selected_code: selection.selectedText,
        start_line: selection.startLine,
        end_line: selection.endLine,
        action,
        project_mode: projectMode,
      },
      (chunk) => {
        accumulated += chunk
        updateResponseContent(id, accumulated)
      },
      () => {
        setResponseDone(id)
      }
    )
  }

  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-blue-50 dark:bg-blue-950 border-t border-blue-200 dark:border-blue-800">
      <span className="text-xs text-blue-700 dark:text-blue-300">
        L{selection.startLine}-{selection.endLine}
      </span>
      <div className="h-3 w-px bg-blue-200 dark:bg-blue-700" />
      {ACTIONS.map((a) => (
        <button
          key={a.key}
          onClick={() => handleAction(a.key)}
          disabled={disabled}
          className={`px-3 py-1 text-xs font-medium text-white rounded transition-colors ${
            disabled
              ? 'bg-gray-400 cursor-not-allowed'
              : 'bg-blue-600 hover:bg-blue-700'
          }`}
        >
          {t(a.labelKey)}
        </button>
      ))}
      {disabled && (
        <span className="text-xs text-amber-600 dark:text-amber-400 animate-pulse">{t('action.waiting')}</span>
      )}
    </div>
  )
}
