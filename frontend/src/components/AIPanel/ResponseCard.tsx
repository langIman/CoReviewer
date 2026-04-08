import { useState } from 'react'
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
  overview: 'text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-900/40 border-green-200 dark:border-green-700',
  visualize: 'text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-900/40 border-purple-200 dark:border-purple-700',
  modules: 'text-orange-700 dark:text-orange-300 bg-orange-50 dark:bg-orange-900/40 border-orange-200 dark:border-orange-700',
}

const LOADING_COLORS: Record<string, string> = {
  overview: 'border-t-green-500',
  visualize: 'border-t-purple-500',
  modules: 'border-t-orange-500',
}

const LOADING_KEYS: Record<string, string> = {
  overview: 'overview.generating',
  visualize: 'visualize.generating',
  modules: 'module.generating',
}

function LoadingCard({ action, t }: { action: string; t: (key: string) => string }) {
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm bg-white dark:bg-gray-800 p-8 flex items-center justify-center gap-3">
      <div className={`w-5 h-5 border-2 border-gray-300 dark:border-gray-600 ${LOADING_COLORS[action] || 'border-t-blue-500'} rounded-full animate-spin`} />
      <span className="text-sm text-gray-400">{t(LOADING_KEYS[action] || 'panel.waitingResponse')}</span>
    </div>
  )
}

export default function ResponseCard({ resp }: { resp: ReviewResponse }) {
  const setHighlightLines = useReviewStore((s) => s.setHighlightLines)
  const { t } = useLanguage()

  if (resp.action === 'overview') {
    if (resp.loading || !resp.content) return <LoadingCard action="overview" t={t} />
  }

  if (resp.action === 'visualize') {
    if (resp.loading || !resp.content) return <LoadingCard action="visualize" t={t} />
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

  if (resp.action === 'modules') {
    if (resp.loading || !resp.content) return <LoadingCard action="modules" t={t} />
    try {
      const data = JSON.parse(resp.content)
      return <ModuleCards modules={data.modules} t={t} />
    } catch {
      return (
        <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-4 text-red-500 text-sm">
          Failed to parse module data
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

function ModuleCards({ modules, t }: { modules: { name: string; description: string; paths: string[] }[]; t: (key: string) => string }) {
  const [expanded, setExpanded] = useState<Record<number, boolean>>({})

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm bg-white dark:bg-gray-800">
      <div className="flex items-center gap-2 px-4 py-2.5 bg-gray-50/80 dark:bg-gray-750 border-b border-gray-100 dark:border-gray-700">
        <span className="text-xs font-semibold px-2.5 py-1 rounded-md border text-orange-700 dark:text-orange-300 bg-orange-50 dark:bg-orange-900/40 border-orange-200 dark:border-orange-700">
          {t('response.modules')}
        </span>
        <span className="text-xs text-gray-400">{modules.length} modules</span>
      </div>
      <div className="p-4 grid gap-3">
        {modules.map((mod, i) => (
          <div key={i} className="border border-gray-200 dark:border-gray-600 rounded-lg overflow-hidden">
            <button
              className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
              onClick={() => setExpanded(prev => ({ ...prev, [i]: !prev[i] }))}
            >
              <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">{mod.name}</span>
              <span className="text-xs text-gray-400 flex-1">{mod.description}</span>
              <svg
                className={`w-4 h-4 text-gray-400 transition-transform ${expanded[i] ? 'rotate-180' : ''}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {expanded[i] && (
              <div className="px-4 pb-3 flex flex-wrap gap-1.5">
                {mod.paths.map((p) => (
                  <span key={p} className="text-xs font-mono px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded">
                    {p}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
