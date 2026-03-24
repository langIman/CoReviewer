import { useReviewStore } from '../../store/useReviewStore'
import ResponseCard from './ResponseCard'

export default function AIPanel() {
  const responses = useReviewStore((s) => s.responses)

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2 bg-gray-50 border-b border-gray-200">
        <span className="text-sm font-semibold text-gray-700">
          AI Review Panel
        </span>
        {responses.length > 0 && (
          <span className="ml-2 text-xs text-gray-400">
            {responses.length} response{responses.length > 1 ? 's' : ''}
          </span>
        )}
      </div>

      <div className="flex-1 overflow-auto p-3 space-y-3">
        {responses.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            Select code on the left, then click an action
          </div>
        ) : (
          responses.map((resp) => (
            <ResponseCard key={resp.id} resp={resp} />
          ))
        )}
      </div>
    </div>
  )
}
