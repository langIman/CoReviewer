import ReactMarkdown from 'react-markdown'
import { useReviewStore } from '../../store/useReviewStore'
import type { ReviewResponse } from '../../types'

const ACTION_LABELS: Record<string, string> = {
  explain: 'Explain',
  review: 'Review',
  suggest: 'Suggest',
}

export default function ResponseCard({ resp }: { resp: ReviewResponse }) {
  const setHighlightLines = useReviewStore((s) => s.setHighlightLines)

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 border-b border-gray-200">
        <span className="text-xs font-semibold text-blue-700 bg-blue-100 px-2 py-0.5 rounded">
          {ACTION_LABELS[resp.action] || resp.action}
        </span>
        <button
          className="text-xs text-gray-500 hover:text-blue-600 font-mono cursor-pointer"
          onClick={() =>
            setHighlightLines({ start: resp.startLine, end: resp.endLine })
          }
        >
          L{resp.startLine}-{resp.endLine}
        </button>
        {resp.loading && (
          <span className="ml-auto text-xs text-gray-400 animate-pulse">
            thinking...
          </span>
        )}
      </div>

      {/* Content */}
      <div className="px-3 py-2 text-sm prose prose-sm max-w-none prose-pre:bg-gray-100 prose-pre:p-2 prose-pre:rounded">
        {resp.content ? (
          <ReactMarkdown>{resp.content}</ReactMarkdown>
        ) : (
          <span className="text-gray-400 text-xs">Waiting for response...</span>
        )}
      </div>
    </div>
  )
}
