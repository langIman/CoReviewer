import MarkdownRenderer from '../Wiki/MarkdownRenderer'
import type { QAMessage, ToolEvent } from '../../types/qa'
import type { CodeRef } from '../../types/wiki'
import { QACodeRefsContext } from './QACodeRefsContext'
import ToolTimeline from './ToolTimeline'

interface BaseProps {
  role: 'user' | 'assistant'
  content: string
  mode?: QAMessage['mode']
  toolEvents?: ToolEvent[]
  codeRefs?: Record<string, CodeRef>
  budgetExhausted?: boolean
  streaming?: boolean
}

export default function MessageBubble({
  role,
  content,
  mode,
  toolEvents = [],
  codeRefs,
  budgetExhausted,
  streaming,
}: BaseProps) {
  if (role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] px-3 py-2 rounded-lg bg-blue-600 text-white text-sm whitespace-pre-wrap break-words">
          {content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[95%] w-full px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100">
        {mode === 'deep' && (
          <ToolTimeline events={toolEvents} budgetExhausted={budgetExhausted} />
        )}
        <QACodeRefsContext.Provider value={codeRefs ?? null}>
          {content ? (
            <MarkdownRenderer content={content} />
          ) : streaming ? (
            <div className="text-gray-400 text-sm italic">思考中…</div>
          ) : null}
        </QACodeRefsContext.Provider>
        {streaming && content && (
          <span className="inline-block w-2 h-4 align-text-bottom bg-gray-400 animate-pulse" />
        )}
      </div>
    </div>
  )
}
