import { useEffect, useRef, useCallback } from 'react'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import { useReviewStore } from '../../store/useReviewStore'

hljs.registerLanguage('python', python)

export default function CodeView() {
  const { file, selection, highlightLines, setSelection } = useReviewStore()
  const codeRef = useRef<HTMLDivElement>(null)

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

  // Handle text selection
  const handleMouseUp = useCallback(() => {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || !codeRef.current) {
      return
    }

    const text = sel.toString()
    if (!text.trim()) return

    // Find start and end line numbers from the selection
    const anchor = sel.anchorNode
    const focus = sel.focusNode

    const findLineNum = (node: Node | null): number => {
      let el = node instanceof HTMLElement ? node : node?.parentElement
      while (el && !el.dataset.line) {
        el = el.parentElement
      }
      return el ? parseInt(el.dataset.line!, 10) : -1
    }

    let startLine = findLineNum(anchor)
    let endLine = findLineNum(focus)

    if (startLine === -1 || endLine === -1) return
    if (startLine > endLine) [startLine, endLine] = [endLine, startLine]

    setSelection({ startLine, endLine, selectedText: text })
  }, [setSelection])

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
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
        Upload a .py file to start reviewing
      </div>
    )
  }

  return (
    <div
      ref={codeRef}
      className="flex-1 overflow-auto font-mono text-sm leading-6"
      onMouseUp={handleMouseUp}
    >
      <table className="w-full border-collapse">
        <tbody>
          {highlightedLines.map((html, i) => {
            const lineNum = i + 1
            const isSelected =
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
                  isSelected
                    ? 'bg-blue-100'
                    : isHighlighted
                      ? 'bg-yellow-50'
                      : 'hover:bg-gray-50'
                }
              >
                <td className="select-none text-right pr-4 pl-3 text-gray-400 w-12 align-top">
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
