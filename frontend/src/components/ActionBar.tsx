import { useReviewStore } from '../store/useReviewStore'
import { streamReview } from '../services/api'

const ACTIONS = [
  { key: 'explain', label: 'AI Explain' },
  { key: 'review', label: 'AI Review' },
  { key: 'suggest', label: 'AI Suggest' },
] as const

export default function ActionBar() {
  const { file, selection } = useReviewStore()

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

    let accumulated = ''
    await streamReview(
      {
        file_name: file.filename,
        full_content: file.content,
        selected_code: selection.selectedText,
        start_line: selection.startLine,
        end_line: selection.endLine,
        action,
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
    <div className="flex items-center gap-2 px-4 py-2 bg-blue-50 border-t border-blue-200">
      <span className="text-xs text-blue-700">
        L{selection.startLine}-{selection.endLine} selected
      </span>
      <div className="h-3 w-px bg-blue-200" />
      {ACTIONS.map((a) => (
        <button
          key={a.key}
          onClick={() => handleAction(a.key)}
          className="px-3 py-1 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700 transition-colors"
        >
          {a.label}
        </button>
      ))}
    </div>
  )
}
