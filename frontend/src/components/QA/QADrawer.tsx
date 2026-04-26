import { useCallback, useEffect, useRef } from 'react'
import { useQAStore } from '../../store/useQAStore'
import ConversationMenu from './ConversationMenu'
import InputBox from './InputBox'
import MessageList from './MessageList'

export default function QADrawer() {
  const open = useQAStore((s) => s.open)
  const widthRatio = useQAStore((s) => s.widthRatio)
  const setWidthRatio = useQAStore((s) => s.setWidthRatio)
  const setOpen = useQAStore((s) => s.setOpen)
  const newConversation = useQAStore((s) => s.newConversation)

  const dragging = useRef(false)
  const lastX = useRef(0)

  const onHandleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragging.current = true
    lastX.current = e.clientX
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      const dx = e.clientX - lastX.current
      lastX.current = e.clientX
      const windowW = window.innerWidth
      // drawer grows when user drags LEFT (dx negative)
      const currentPx = widthRatio * windowW
      const nextPx = currentPx - dx
      setWidthRatio(nextPx / windowW)
    }
    const onUp = () => {
      if (!dragging.current) return
      dragging.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    return () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
  }, [widthRatio, setWidthRatio])

  if (!open) return null

  return (
    <aside
      className="flex flex-row-reverse border-l border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 flex-shrink-0"
      style={{ width: `${widthRatio * 100}vw` }}
    >
      {/* 拖拽把手在抽屉左侧 */}
      <div
        className="w-1.5 cursor-col-resize bg-gray-200 dark:bg-gray-700 hover:bg-blue-400 dark:hover:bg-blue-500 active:bg-blue-500 transition-colors flex-shrink-0"
        onMouseDown={onHandleMouseDown}
      />
      <div className="flex flex-col flex-1 min-w-0">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 flex-shrink-0">
          <ConversationMenu />
          <button
            onClick={newConversation}
            className="text-xs text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 px-2 py-1 rounded"
            title="新建对话"
          >
            + 新建
          </button>
          <button
            onClick={() => setOpen(false)}
            className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400"
            aria-label="关闭问答面板"
            title="关闭"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 3 L13 13 M13 3 L3 13" />
            </svg>
          </button>
        </div>
        <MessageList />
        <InputBox />
      </div>
    </aside>
  )
}
