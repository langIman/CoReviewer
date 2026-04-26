import { useEffect, useRef, useState } from 'react'
import { useQAStore } from '../../store/useQAStore'
import { useWikiStore } from '../../store/useWikiStore'

function relativeTime(iso: string): string {
  try {
    const t = new Date(iso).getTime()
    const diff = Date.now() - t
    if (diff < 60_000) return '刚刚'
    if (diff < 3600_000) return `${Math.floor(diff / 60_000)} 分钟前`
    if (diff < 86400_000) return `${Math.floor(diff / 3600_000)} 小时前`
    const days = Math.floor(diff / 86400_000)
    if (days < 30) return `${days} 天前`
    return new Date(iso).toLocaleDateString()
  } catch {
    return iso
  }
}

export default function ConversationMenu() {
  const currentId = useQAStore((s) => s.currentConversationId)
  const currentTitle = useQAStore((s) => s.currentTitle)
  const conversations = useQAStore((s) => s.conversations)
  const loadConversations = useQAStore((s) => s.loadConversations)
  const selectConversation = useQAStore((s) => s.selectConversation)
  const deleteConversation = useQAStore((s) => s.deleteConversation)
  const newConversation = useQAStore((s) => s.newConversation)
  const projectName = useWikiStore((s) => s.projectName)

  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (projectName) void loadConversations(projectName)
  }, [projectName, loadConversations])

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const title = currentTitle || (currentId ? '（未命名）' : '新对话')

  return (
    <div ref={rootRef} className="relative flex-1 min-w-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-1 text-sm text-gray-800 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 rounded px-2 py-1"
        title="切换会话"
      >
        <span className="truncate flex-1 text-left">{title}</span>
        <span className="text-gray-400 text-xs">▼</span>
      </button>
      {open && (
        <div className="absolute left-0 right-0 top-full mt-1 z-20 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded shadow-lg max-h-80 overflow-y-auto">
          <button
            onClick={() => {
              newConversation()
              setOpen(false)
            }}
            className="w-full text-left px-3 py-2 text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30 border-b border-gray-200 dark:border-gray-700"
          >
            + 新建对话
          </button>
          {conversations.length === 0 ? (
            <div className="px-3 py-3 text-xs text-gray-400 text-center">暂无历史</div>
          ) : (
            conversations.map((c) => (
              <div
                key={c.id}
                className={`group flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-700/60 cursor-pointer ${
                  c.id === currentId ? 'bg-blue-50 dark:bg-blue-900/30' : ''
                }`}
                onClick={() => {
                  void selectConversation(c.id)
                  setOpen(false)
                }}
              >
                <div className="flex-1 min-w-0">
                  <div className="truncate text-gray-800 dark:text-gray-100">
                    {c.title || '（未命名）'}
                  </div>
                  <div className="text-[11px] text-gray-400">{relativeTime(c.updated_at)}</div>
                </div>
                <button
                  className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 text-sm px-1"
                  onClick={(e) => {
                    e.stopPropagation()
                    if (window.confirm(`删除会话「${c.title}」？`)) {
                      void deleteConversation(c.id)
                    }
                  }}
                  title="删除"
                >
                  🗑
                </button>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
