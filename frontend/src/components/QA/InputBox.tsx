import { useState, type KeyboardEvent } from 'react'
import { useQAStore } from '../../store/useQAStore'
import { useWikiStore } from '../../store/useWikiStore'
import ModeToggle from './ModeToggle'

export default function InputBox() {
  const [text, setText] = useState('')
  const streaming = useQAStore((s) => s.streaming)
  const mode = useQAStore((s) => s.mode)
  const setMode = useQAStore((s) => s.setMode)
  const ask = useQAStore((s) => s.ask)
  const cancelStream = useQAStore((s) => s.cancelStream)
  const projectName = useWikiStore((s) => s.projectName)

  const canSend = text.trim().length > 0 && !!projectName && !streaming

  const send = () => {
    if (!canSend || !projectName) return
    const q = text
    setText('')
    void ask(q, projectName)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 px-3 py-2 bg-white dark:bg-gray-900 flex-shrink-0">
      <div className="flex items-center justify-between mb-2">
        <ModeToggle mode={mode} disabled={streaming} onChange={setMode} />
        {streaming && (
          <button
            onClick={cancelStream}
            className="text-xs text-red-600 dark:text-red-400 hover:underline"
          >
            ✕ 取消
          </button>
        )}
      </div>
      <div className="flex items-end gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder={
            projectName
              ? '提问…（Enter 发送，Shift+Enter 换行）'
              : '请先上传项目'
          }
          disabled={streaming || !projectName}
          className="flex-1 resize-none rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm px-2 py-1.5 text-gray-800 dark:text-gray-100 placeholder-gray-400 disabled:opacity-60 focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
        <button
          onClick={send}
          disabled={!canSend}
          className="px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          发送
        </button>
      </div>
    </div>
  )
}
