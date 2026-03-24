import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useReviewStore } from '../../store/useReviewStore'
import { useLanguage } from '../../i18n/LanguageContext'
import type { ReviewResponse } from '../../types'
import FlowChart from '../Diagrams/FlowChart'

const ACTION_COLORS: Record<string, string> = {
  explain: 'text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/40 border-blue-200 dark:border-blue-700',
  review: 'text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/40 border-amber-200 dark:border-amber-700',
  suggest: 'text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-900/40 border-emerald-200 dark:border-emerald-700',
}

export default function ResponseCard({ resp }: { resp: ReviewResponse }) {
  const setHighlightLines = useReviewStore((s) => s.setHighlightLines)
  const { t } = useLanguage()

  // 可视化类型：直接渲染 FlowChart
  if (resp.action === 'visualize') {
    if (resp.loading || !resp.content) {
      return (
        <div className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm bg-white dark:bg-gray-800 p-8 flex items-center justify-center gap-3">
          <div className="w-5 h-5 border-2 border-gray-300 dark:border-gray-600 border-t-purple-500 rounded-full animate-spin" />
          <span className="text-sm text-gray-400">{t('visualize.generating')}</span>
        </div>
      )
    }
    try {
      const flowData = JSON.parse(resp.content)
      return <FlowChart data={flowData} />
    } catch {
      return (
        <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-4 text-red-500 text-sm">
          Failed to parse flow data
        </div>
      )
    }
  }

  const colorClass = ACTION_COLORS[resp.action] || 'text-gray-700 bg-gray-50 border-gray-200'
  const label = t(`response.${resp.action}`) || resp.action

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm bg-white dark:bg-gray-800">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-gray-50/80 dark:bg-gray-750 border-b border-gray-100 dark:border-gray-700">
        <span className={`text-xs font-semibold px-2.5 py-1 rounded-md border ${colorClass}`}>
          {label}
        </span>
        <button
          className="text-xs text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 font-mono cursor-pointer transition-colors"
          onClick={() =>
            setHighlightLines({ start: resp.startLine, end: resp.endLine })
          }
        >
          L{resp.startLine}-{resp.endLine}
        </button>
        {resp.loading && (
          <span className="ml-auto text-xs text-gray-400 animate-pulse">
            {t('panel.thinking')}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="px-5 py-4 text-sm markdown-body">
        {resp.content ? (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ children }) => <h2 className="text-base font-bold text-gray-800 dark:text-gray-100 mt-4 mb-2 pb-1 border-b border-gray-100 dark:border-gray-700">{children}</h2>,
              h2: ({ children }) => <h3 className="text-sm font-bold text-gray-800 dark:text-gray-100 mt-4 mb-2">{children}</h3>,
              h3: ({ children }) => <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mt-3 mb-1.5">{children}</h4>,
              p: ({ children }) => <p className="text-gray-600 dark:text-gray-300 leading-relaxed mb-3">{children}</p>,
              ul: ({ children }) => <ul className="space-y-1.5 mb-3 ml-1">{children}</ul>,
              ol: ({ children }) => <ol className="space-y-1.5 mb-3 ml-1 list-decimal list-inside">{children}</ol>,
              li: ({ children }) => (
                <li className="text-gray-600 dark:text-gray-300 leading-relaxed flex gap-1.5">
                  <span className="text-gray-300 dark:text-gray-600 mt-0.5 shrink-0">•</span>
                  <span>{children}</span>
                </li>
              ),
              strong: ({ children }) => <strong className="font-semibold text-gray-800 dark:text-gray-100">{children}</strong>,
              code: ({ className, children }) => {
                const isBlock = className?.includes('language-')
                if (isBlock) {
                  return <code className="text-[13px]">{children}</code>
                }
                return (
                  <code className="text-[13px] text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-900/30 px-1.5 py-0.5 rounded font-mono">
                    {children}
                  </code>
                )
              },
              pre: ({ children }) => (
                <pre className="bg-gray-900 dark:bg-gray-950 text-gray-100 rounded-lg p-4 mb-3 overflow-x-auto text-[13px] leading-relaxed">
                  {children}
                </pre>
              ),
              table: ({ children }) => (
                <div className="overflow-x-auto mb-3">
                  <table className="min-w-full text-sm border border-gray-200 dark:border-gray-600 rounded-lg overflow-hidden">
                    {children}
                  </table>
                </div>
              ),
              thead: ({ children }) => <thead className="bg-gray-50 dark:bg-gray-700">{children}</thead>,
              th: ({ children }) => <th className="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 border-b border-gray-200 dark:border-gray-600">{children}</th>,
              td: ({ children }) => <td className="px-3 py-2 text-gray-600 dark:text-gray-300 border-b border-gray-100 dark:border-gray-700">{children}</td>,
              blockquote: ({ children }) => (
                <blockquote className="border-l-3 border-blue-300 dark:border-blue-600 pl-4 py-1 my-3 text-gray-500 dark:text-gray-400 italic">
                  {children}
                </blockquote>
              ),
            }}
          >
            {resp.content}
          </ReactMarkdown>
        ) : (
          <div className="flex items-center gap-2 text-gray-400 text-xs py-2">
            <div className="w-4 h-4 border-2 border-gray-300 dark:border-gray-600 border-t-blue-500 rounded-full animate-spin" />
            {t('panel.waitingResponse')}
          </div>
        )}
      </div>
    </div>
  )
}
