import { useEffect, useMemo, useRef } from 'react'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import type { CodeRef } from '../../types/wiki'
import { useWikiStore } from '../../store/useWikiStore'

hljs.registerLanguage('python', python)

interface Props {
  codeRef: CodeRef
}

export default function CodeSnippet({ codeRef }: Props) {
  const content = useWikiStore((s) => s.projectFiles[codeRef.file])
  const containerRef = useRef<HTMLDivElement>(null)

  const lines = useMemo(() => {
    if (!content) return [] as string[]
    return content.split('\n')
  }, [content])

  const highlighted = useMemo(() => {
    if (!content) return [] as string[]
    return lines.map((line) => {
      if (!line.trim()) return '&nbsp;'
      try {
        return hljs.highlight(line, { language: 'python' }).value
      } catch {
        return line
      }
    })
  }, [lines, content])

  useEffect(() => {
    if (!containerRef.current) return
    const target = containerRef.current.querySelector(
      `[data-line="${codeRef.start_line}"]`
    )
    target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [codeRef])

  if (!content) {
    return (
      <div className="flex-1 flex items-center justify-center text-sm text-gray-500 dark:text-gray-400 p-4">
        源文件未加载：<code className="font-mono mx-1">{codeRef.file}</code>
        。请重新上传项目以使用代码视图。
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-auto font-mono text-[13px] leading-6 bg-white dark:bg-gray-900 dark:text-gray-200"
    >
      <table className="w-full border-collapse">
        <tbody>
          {highlighted.map((html, i) => {
            const lineNum = i + 1
            const isHighlighted =
              lineNum >= codeRef.start_line && lineNum <= codeRef.end_line
            return (
              <tr
                key={lineNum}
                data-line={lineNum}
                className={
                  isHighlighted
                    ? 'bg-yellow-100 dark:bg-yellow-900/30'
                    : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                }
              >
                <td className="text-right pr-3 pl-3 text-gray-400 dark:text-gray-500 w-12 select-none align-top">
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
