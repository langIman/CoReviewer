import { useEffect, useRef, useState, useCallback } from 'react'
import { useReviewStore } from '../../store/useReviewStore'
import { useLanguage } from '../../i18n/LanguageContext'
import ResponseCard from './ResponseCard'

export default function AIPanel() {
  const responses = useReviewStore((s) => s.responses)
  const { t } = useLanguage()
  const scrollRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [showArrow, setShowArrow] = useState(false)
  const [modelName, setModelName] = useState('')

  // 获取当前模型名称
  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((d) => setModelName(d.model || ''))
      .catch(() => {})
  }, [])

  // 检测是否在底部
  const checkAtBottom = useCallback(() => {
    const el = scrollRef.current
    if (!el) return true
    return el.scrollHeight - el.scrollTop - el.clientHeight < 40
  }, [])

  // 用户滚动时判断是否脱离底部
  const handleScroll = useCallback(() => {
    const atBottom = checkAtBottom()
    setAutoScroll(atBottom)
    setShowArrow(!atBottom && responses.length > 0)
  }, [checkAtBottom, responses.length])

  // 流式生成中内容更新时，如果 autoScroll 则保持底部
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  })

  // 新增回答时重新开启 autoScroll
  const prevCount = useRef(responses.length)
  useEffect(() => {
    if (responses.length > prevCount.current) {
      setAutoScroll(true)
    }
    prevCount.current = responses.length
  }, [responses.length])

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
      setAutoScroll(true)
      setShowArrow(false)
    }
  }, [])

  return (
    <div className="flex flex-col h-full bg-gray-50/50 dark:bg-gray-900 relative">
      <div className="px-4 py-2.5 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 relative flex items-center justify-center">
        <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">
          {t('panel.title')}
        </span>
        <div className="absolute right-4 flex items-center gap-2">
          {responses.length > 0 && (
            <span className="text-xs text-gray-400">
              {responses.length}
            </span>
          )}
          {modelName && (
            <span className="text-[10px] text-gray-300 dark:text-gray-500">
              {t('panel.modelHint').replace('{model}', modelName)}
            </span>
          )}
        </div>
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-auto p-4 space-y-4"
        onScroll={handleScroll}
      >
        {responses.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-2">
            <div className="text-3xl">&#8592;</div>
            <p className="text-sm">{t('panel.empty')}</p>
          </div>
        ) : (
          responses.map((resp) => (
            <ResponseCard key={resp.id} resp={resp} />
          ))
        )}
      </div>

      {/* 回到底部箭头 */}
      {showArrow && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-6 right-6 w-9 h-9 bg-blue-600 hover:bg-blue-700 text-white rounded-full flex items-center justify-center transition-all shadow-[0_4px_14px_rgba(37,99,235,0.5)]"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M8 3v10M4 9l4 4 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      )}
    </div>
  )
}
