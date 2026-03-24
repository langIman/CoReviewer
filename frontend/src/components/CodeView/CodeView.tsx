import { useEffect, useRef, useCallback, useState } from 'react'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import { useReviewStore } from '../../store/useReviewStore'
import { useLanguage } from '../../i18n/LanguageContext'

hljs.registerLanguage('python', python)

export default function CodeView() {
  const { file, selection, highlightLines, setSelection } = useReviewStore()
  const { t } = useLanguage()
  const codeRef = useRef<HTMLDivElement>(null)
  // 实时拖选状态
  const [dragging, setDragging] = useState(false)
  const [dragRange, setDragRange] = useState<{ start: number; end: number } | null>(null)
  const dragStartLine = useRef<number | null>(null)
  const didDrag = useRef(false)

  // Split content into lines
  const lines = file ? file.content.split('\n') : []

  // Highlight each line
  const highlightedLines = lines.map((line) => {
    if (!line.trim()) return '&nbsp;'
    try {
      return hljs.highlight(line, { language: 'python' }).value
    } catch {
      return line
    }
  })

  // 从 DOM 节点找到行号
  const findLineNum = useCallback((node: Node | null): number => {
    let el = node instanceof HTMLElement ? node : node?.parentElement
    while (el && !el.dataset.line) {
      el = el.parentElement
    }
    return el ? parseInt(el.dataset.line!, 10) : -1
  }, [])

  // 从鼠标事件找到行号
  const getLineFromEvent = useCallback((e: React.MouseEvent): number => {
    const target = e.target as HTMLElement
    let el: HTMLElement | null = target
    while (el && !el.dataset.line) {
      el = el.parentElement
    }
    return el ? parseInt(el.dataset.line!, 10) : -1
  }, [])

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    // 只响应左键
    if (e.button !== 0) return
    const line = getLineFromEvent(e)
    if (line === -1) return
    dragStartLine.current = line
    didDrag.current = false
    setDragging(true)
    setDragRange({ start: line, end: line })
  }, [getLineFromEvent])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging || dragStartLine.current === null) return
    const line = getLineFromEvent(e)
    if (line === -1) return
    if (line !== dragStartLine.current) didDrag.current = true
    const start = Math.min(dragStartLine.current, line)
    const end = Math.max(dragStartLine.current, line)
    setDragRange({ start, end })
  }, [dragging, getLineFromEvent])

  const handleMouseUp = useCallback(() => {
    if (!dragging || !dragRange || dragStartLine.current === null) {
      return
    }

    setDragging(false)
    dragStartLine.current = null

    // 没有拖动 = 单击 = 取消选区
    if (!didDrag.current) {
      setDragRange(null)
      setSelection(null)
      return
    }

    // 获取选中的文本内容
    const selectedLines = lines.slice(dragRange.start - 1, dragRange.end)
    const selectedText = selectedLines.join('\n')

    if (!selectedText.trim()) {
      setDragRange(null)
      setSelection(null)
      return
    }

    setSelection({
      startLine: dragRange.start,
      endLine: dragRange.end,
      selectedText,
    })
    setDragRange(null)

    // 清除浏览器原生选区
    window.getSelection()?.removeAllRanges()
  }, [dragging, dragRange, lines, setSelection])

  // Scroll to highlighted lines
  useEffect(() => {
    if (highlightLines && codeRef.current) {
      const lineEl = codeRef.current.querySelector(
        `[data-line="${highlightLines.start}"]`
      )
      lineEl?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [highlightLines])

  if (!file) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500 text-sm">
        {t('code.empty')}
      </div>
    )
  }

  return (
    <div
      ref={codeRef}
      className="flex-1 overflow-auto font-mono text-sm leading-6 code-view-area select-none dark:bg-gray-900 dark:text-gray-200"
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onContextMenu={(e) => e.preventDefault()}
    >
      <table className="w-full border-collapse">
        <tbody>
          {highlightedLines.map((html, i) => {
            const lineNum = i + 1

            // 拖选中实时高亮
            const isDragging =
              dragRange &&
              dragging &&
              lineNum >= dragRange.start &&
              lineNum <= dragRange.end

            const isSelected =
              !dragging &&
              selection &&
              lineNum >= selection.startLine &&
              lineNum <= selection.endLine

            const isHighlighted =
              highlightLines &&
              lineNum >= highlightLines.start &&
              lineNum <= highlightLines.end

            return (
              <tr
                key={lineNum}
                data-line={lineNum}
                className={
                  isDragging
                    ? 'bg-blue-100 dark:bg-blue-900/50'
                    : isSelected
                      ? 'bg-blue-100 dark:bg-blue-900/50'
                      : isHighlighted
                        ? 'bg-yellow-50 dark:bg-yellow-900/30'
                        : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                }
              >
                <td className="text-right pr-4 pl-3 text-gray-400 dark:text-gray-500 w-12 align-top">
                  {lineNum}
                </td>
                <td
                  className="pr-4 whitespace-pre"
                  dangerouslySetInnerHTML={{ __html: html }}
                />
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
